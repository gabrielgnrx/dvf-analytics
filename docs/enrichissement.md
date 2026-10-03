# Enrichissement par données ouvertes

DVF décrit la transaction (prix, surface, localisation) mais rien de
l'environnement du bien. Quatre sources publiques sont croisées avec les ventes
pour répondre à des questions métier : combien vaut la proximité d'une gare ?
Le Grand Paris Express est-il déjà dans les prix ? Quel lien entre prix,
revenus des habitants et qualité énergétique du parc ?

## Sources

| Table brute (`raw`) | Contenu | Producteur | Accès |
|---|---|---|---|
| `ref_gares` | Gares et stations en service (métro, RER, train, tram, VAL) | Île-de-France Mobilités | Export CSV « emplacement des gares IDF » |
| `ref_gares_projet` | Gares et stations en projet, dont les lignes 15 à 18 du Grand Paris Express | Île-de-France Mobilités | Export CSV « projets_arrets_idf » (aussi référencé sur data.gouv) |
| `ref_revenus_communes` | Revenu disponible par unité de consommation (médiane, déciles) | INSEE, Filosofi 2021 | CSV data.gouv « Revenu des français à la commune » |
| `ref_dpe_communes` | Nombre de DPE par commune et par étiquette (A à G) | ADEME, DPE logements existants | API data-fair, agrégation côté serveur |

Chargement : `ingestion/enrichment.py`, tâche Airflow `load_enrichment`
exécutée en parallèle de l'ingestion DVF. Volumes faibles (environ 11 000
lignes au total), rechargement complet à chaque exécution. L'URL du fichier
revenus est relue sur l'API data.gouv à chaque fois, car elle change à chaque
republication.

## Transformations dbt

- `stg_ref__gares` : une ligne par gare physique (la source répète la gare pour
  chaque ligne desservie), mode le plus lourd, indicateur « transport lourd »
  (métro, RER, train, VAL).
- `stg_ref__gares_projet` : gares en projet hors bus, indicateur Grand Paris
  Express (lignes 15, 16, 17, 18).
- `stg_ref__revenus_communes`, `stg_ref__dpe_communes` : typage, part des
  passoires thermiques (F et G) et des logements A et B.
- `int_geo__proximite_transports` : pour chaque vente géolocalisée, distance à
  la gare lourde la plus proche, nombre de gares à moins de 1 km et distance à
  la future gare du Grand Paris Express la plus proche. Jointure spatiale
  BigQuery (`ST_DWITHIN`, `ST_DISTANCE`) sur les points distincts arrondis à
  environ 10 m, distances plafonnées à 5 km (gares) et 10 km (GPE).
- `fact_transactions` reçoit les distances et des tranches lisibles,
  `dim_geo` les revenus et indicateurs DPE de la commune.
- `mart_proximite_gpe` : prix au m² médian par année, zone, type de bien et
  distance à une future gare du GPE (hors Paris), avec l'évolution depuis la
  première année.
- Test `assert_couverture_enrichissement` : au moins 95 % des ventes doivent
  être enrichies pour chaque source, sinon le build échoue (jointure cassée,
  changement de format).

Couverture observée sur les ventes simples : 100 % pour les revenus et le DPE,
99 % pour les transports (ventes non géolocalisées exclues).

## Constats (Île-de-France, 2021 à 2025)

**Proximité d'une gare (appartements, prix au m² médian)**

| Zone | Moins de 500 m | 500 m à 1 km | 1 à 2 km | Plus de 2 km |
|---|---:|---:|---:|---:|
| Petite couronne | 6 452 € | 5 563 € | 4 200 € | 3 550 € |
| Grande couronne | 3 656 € | 3 346 € | 3 220 € | 3 421 € |

En petite couronne, un appartement à moins de 500 m d'une gare se vend environ
80 % plus cher au m² qu'un appartement à plus de 2 km. L'écart mêle l'effet de
la gare et celui des communes les mieux desservies (proches de Paris). En
grande couronne, l'effet est faible et non monotone : la tranche « plus de
2 km » contient des communes résidentielles recherchées.

**Grand Paris Express (hors Paris, évolution du prix au m² médian 2021 à 2025)**

| Zone, type | Moins de 800 m | 800 m à 1,5 km | 1,5 à 3 km | Plus de 3 km |
|---|---:|---:|---:|---:|
| Petite couronne, appartements | -7,3 % | -8,5 % | -5,1 % | -0,5 % |
| Petite couronne, maisons | -7,3 % | -9,0 % | -5,9 % | -6,2 % |
| Grande couronne, appartements | -0,8 % | -3,3 % | -4,6 % | -0,2 % |

Sur 2021 à 2025, les biens proches d'une future gare ne se sont pas valorisés
plus vite que les autres : en petite couronne, ils ont même davantage baissé
pendant le retournement du marché. Deux lectures possibles : l'anticipation
était déjà intégrée aux prix avant 2021, ou l'effet n'apparaîtra qu'à la mise
en service (ligne 15 Sud fin 2026). À suivre avec les prochains millésimes DVF.

**Revenus et DPE (corrélation entre indicateur communal et prix au m² médian,
communes avec au moins 30 ventes)**

| Zone | Communes | Revenu médian | Part DPE F-G |
|---|---:|---:|---:|
| Paris (arrondissements) | 20 | 0,86 | 0,82 |
| Petite couronne | 123 | 0,69 | 0,48 |
| Grande couronne | 864 | 0,62 | -0,37 |

Le revenu des habitants suit fortement le prix au m². La part de passoires
thermiques est corrélée positivement au prix à Paris et en petite couronne :
les quartiers anciens et chers (immeubles haussmanniens, petites surfaces) ont
davantage de DPE F et G. En grande couronne, la relation s'inverse.

## Apport au modèle de prix

| Test 2025 | MAE (€/m²) | MdAPE | Part à ±10 % | R² (log) |
|---|---:|---:|---:|---:|
| Modèle sans enrichissement | 1 023 | 13,0 % | 39,7 % | 0,801 |
| Modèle enrichi | 1 015 | 12,8 % | 40,4 % | 0,804 |

Le gain est réel mais modeste. Les variables communales (revenus, DPE) sont
redondantes avec le code commune déjà présent dans le modèle : elles prennent
une part importante de l'importance (le rapport interdécile D9/D1 sert de
signature de la commune) sans apporter d'information nouvelle. Le gain vient
des variables fines, à l'échelle du logement (distances aux gares). Pour aller
plus loin, il faudrait des données au niveau du bien (DPE rapproché à
l'adresse, étage) ou du quartier (IRIS).

## Limites

- La liste des gares en service est celle d'aujourd'hui : une vente de 2021
  près d'une gare ouverte en 2024 est comptée comme desservie.
- Distances à vol d'oiseau, pas en temps de marche.
- Revenus : un seul millésime (2021), appliqué à toutes les années.
- DPE : stock de diagnostics réalisés depuis juillet 2021, pas l'ensemble du
  parc ; les logements diagnostiqués sont surtout ceux vendus ou loués.
- Les constats sont des corrélations, pas des effets causaux.
