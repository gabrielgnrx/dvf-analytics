# Couche BI — Power BI

## Connexion

Power BI Desktop > Obtenir les données > Google BigQuery > connexion avec le
compte Google du projet `data-510311`. Mode **Import** (volume modéré, DAX
complet). Tables à charger :

| Table | Dataset | Rôle |
|---|---|---|
| fact_transactions | analytics_marts | Faits, grain mutation |
| dim_temps | analytics_marts | Calendrier (marquer comme table de dates sur `date`) |
| dim_geo | analytics_marts | Commune, département, zone |
| dim_bien | analytics_marts | Type x pièces x tranche de surface |
| mart_ecarts_prix | analytics_marts | Écarts au prix prédit par le modèle |

## Modèle en étoile

- fact_transactions[date_key] → dim_temps[date_key] (plusieurs à un)
- fact_transactions[geo_key] → dim_geo[geo_key]
- fact_transactions[bien_key] → dim_bien[bien_key]
- mart_ecarts_prix[transaction_id] → fact_transactions[transaction_id] (un à un, filtre unidirectionnel depuis le fait)

Filtres unidirectionnels des dimensions vers le fait. Masquer les clés techniques.

## Mesures

Voir `mesures.dax` : à créer dans une table de mesures `_Mesures`.

## Sécurité au niveau des lignes (RLS)

Rôle par zone, sur dim_geo :

| Rôle | Filtre DAX sur dim_geo |
|---|---|
| Paris | `[zone] = "Paris"` |
| Petite couronne | `[zone] = "Petite couronne"` |
| Grande couronne | `[zone] = "Grande couronne"` |

Scénario : un directeur d'agence ne voit que son périmètre. Tester avec
« Modélisation > Afficher comme ».

## Pages du rapport

1. **Synthèse exécutive** : cartes KPI (Nb ventes, Prix m² médian, Évolution
   prix m² %, Évolution volume %), courbe du prix m² médian 12 mois glissants
   par zone, carte des communes colorée par prix m² médian.
2. **Analyse marché** : matrice département x type de bien, histogramme des
   surfaces, top / flop communes (Rang commune prix m²), segments T1 à T5+.
3. **Modèle et écarts** : répartition par positionnement_prix, nuage prix réel
   vs prix prédit, communes où le marché est le plus dispersé.
4. **Qualité des données** : Part ventes fiables %, volumes par type de bien,
   lien vers le rapport de profilage.
