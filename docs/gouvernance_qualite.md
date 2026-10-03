# Gouvernance et qualité des données

Ce document décrit comment la donnée DVF est contrôlée, transformée et
exposée, de la source publique jusqu'au rapport Power BI.

## 1. Lignage

| Étape | Objet | Outil | Contrôle |
|---|---|---|---|
| Source | geo-dvf (data.gouv), CSV par année et département | `ingestion/download.py` | Fichiers absents journalisés (ex. 2020 retiré de « latest ») |
| Atterrissage | `raw.dvf_mutations` (tout en STRING) | `ingestion/load_to_bq.py` | Rechargement complet idempotent (WRITE_TRUNCATE) |
| Profilage | rapport Markdown | `exploration/profiling.py` | Nuls, multi-lots, types de locaux, valeurs suspectes |
| Typage | `stg_dvf__mutations` | dbt (vue) | Tests not_null, plages, valeurs acceptées |
| Grain mutation | `int_dvf__mutations` | dbt (vue) | Unicité de `id_mutation`, typologie contrôlée |
| Étoile | `fact_transactions`, `dim_temps`, `dim_geo`, `dim_bien` | dbt (tables) | Unicité des clés, intégrité référentielle fait → dimensions |
| Modèle | `analytics_ml.predictions_prix_m2` | `ml/train_prix_m2.py` | Évaluation sur 2025 jamais vue, baseline de référence |
| Restitution | `mart_ecarts_prix`, rapport Power BI | dbt + Power BI | Relations, RLS par zone |

## 2. Règles de qualité appliquées

| Règle | Où | Motif |
|---|---|---|
| Ventes uniquement (`nature_mutation = 'Vente'`) | staging | Exclut échanges, adjudications, expropriations, VEFA |
| Valeur foncière strictement positive, date valide | staging | Lignes inexploitables |
| Dédoublonnage des lignes strictement identiques | intermediate | Doublons présents dans la source |
| Agrégation au grain mutation, valeur prise une seule fois | intermediate | La valeur foncière est répétée sur chaque ligne d'une mutation |
| Dédoublonnage des locaux répétés par nature de culture | intermediate | Évite de compter deux fois une surface |
| Prix au m² seulement pour une vente d'un seul logement de 9 m² ou plus | intermediate / fait | Le prix d'une vente en bloc n'est pas ventilable |
| Indicateur `est_prix_m2_fiable` (1 000 à 30 000 €/m²) | fait | Signaler plutôt que supprimer : la décision reste visible dans le BI |

## 3. Tests automatisés (dbt)

42 contrôles exécutés à chaque `dbt build` : 41 réussis, 1 avertissement
documenté (8 ventes à valeur symbolique dont le prix au m² arrondi vaut 0,
conservées et marquées non fiables).

Familles de tests : `not_null`, `unique`, `accepted_values`,
`dbt_utils.accepted_range`, `relationships` (chaque clé du fait existe dans sa
dimension).

Sources d'enrichissement (depuis le 3 octobre 2026) : unicité des ventes dans
`int_geo__proximite_transports`, plages de distances (0 à 5 km, 0 à 10 km),
plages de revenus et de parts DPE, valeurs autorisées des tranches de
distance, unicité du grain de `mart_proximite_gpe`, et un test singulier de
couverture (`tests/assert_couverture_enrichissement.sql`) : le build échoue si
moins de 95 % des ventes sont enrichies par l'une des sources.

## 4. Indicateurs de qualité (Île-de-France, 2021 à 2025)

| Indicateur | Valeur |
|---|---:|
| Lignes brutes chargées | 2 433 220 |
| Ventes après agrégation | 884 567 |
| Part de ventes « simples » (un seul logement) | 77,6 % |
| Part de prix au m² fiables | 76,4 % |
| Ventes écartées du calcul de prix au m² | 208 798 |
| Ventes scorées par le modèle | 675 769 |

Ces indicateurs sont recalculés en continu dans la page « Qualité des données »
du rapport Power BI.

## 5. Sécurité et accès

- Aucun secret dans le dépôt : `.env`, clés et caches exclus par `.gitignore`.
- Authentification OAuth (Cloud Shell ou `gcloud auth application-default login`),
  sans clé de service account stockée sur poste.
- Sécurité au niveau des lignes dans Power BI : rôles Paris, Petite couronne et
  Grande couronne, filtre `dim_geo[zone]`. Scénario : un responsable d'agence ne
  voit que son territoire.
- Contrôle de la RLS (« Afficher comme ») : le rôle Paris ne voit que 204 315
  ventes, toutes à Paris ; le rôle Grande couronne en voit 393 662, réparties
  sur les Yvelines, le Val-d'Oise, l'Essonne et la Seine-et-Marne. Ces volumes
  correspondent exactement aux totaux par département.

## 6. Limites connues

- DVF ne décrit ni l'étage, ni l'état du bien, ni sa performance énergétique.
- Les ventes en bloc et les biens mixtes n'ont pas de prix au m² exploitable.
- Le bac à sable BigQuery fait expirer les tables après 60 jours : la chaîne
  est reproductible de bout en bout pour les recréer.
