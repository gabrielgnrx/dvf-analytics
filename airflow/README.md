# Orchestration Airflow

Le pipeline complet tourne dans Airflow (Docker, LocalExecutor), une fois par
mois, le 1er à 6 h.

```
download_geo_dvf → load_raw_bigquery → check_raw_landing ┐
load_enrichment (gares, GPE, revenus, DPE) ──────────────┴→ dbt_transform (une tâche par modèle dbt, tests après chaque modèle)
    → train_price_model → dbt_ml_mart → log_run
```

| Tâche | Rôle |
|---|---|
| `download_geo_dvf` | Télécharge les CSV geo-dvf du périmètre (cache local, idempotent) |
| `load_raw_bigquery` | Recharge `raw.dvf_mutations` |
| `check_raw_landing` | Contrôle bloquant : au moins 1 M lignes et les 8 départements présents |
| `load_enrichment` | Recharge `raw.ref_*` : gares IDFM, Grand Paris Express, revenus INSEE, DPE ADEME |
| `dbt_transform` | Seeds, staging, intermediate, étoile ; chaque modèle suivi de ses tests (Astronomer Cosmos) |
| `train_price_model` | Réentraîne LightGBM et réécrit `analytics_ml.predictions_prix_m2` |
| `dbt_ml_mart` | Reconstruit `mart_ecarts_prix` et ses tests |
| `log_run` | Ajoute une ligne de suivi dans `analytics_ops.pipeline_runs` |

Pourquoi tous les mois : DVF est publié deux fois par an, mais les tables du
bac à sable BigQuery expirent au bout de 60 jours. Le rythme mensuel garde
l'entrepôt et le rapport Power BI toujours disponibles.

## Démarrage (Windows, Docker Desktop lancé)

Dans un terminal PowerShell, depuis ce dossier `airflow` :

```powershell
copy .env.example .env          # puis renseigner GCP_PROJECT_ID et le mot de passe admin
docker compose build            # construit l'image (5 à 10 min la première fois)
docker compose run --rm gcloud-auth
docker compose up -d
```

`gcloud-auth` affiche un lien : l'ouvrir, se connecter avec le compte Google
du projet, puis recoller le code affiché. La connexion est stockée dans un
volume Docker et partagée en lecture seule avec Airflow. Aucune clé de service
account n'est créée.

Interface : http://localhost:8080 (identifiants définis dans `.env`). Le DAG
`dvf_pipeline` est actif dès le démarrage et lance une première exécution.

Arrêt : `docker compose down` (les données et l'historique sont conservés).

## Choix techniques

- **Astronomer Cosmos** transforme le projet dbt en tâches Airflow : chaque
  modèle et ses tests apparaissent dans le graphe, avec relance ciblée en cas
  d'échec.
- **dbt dans son propre environnement virtuel** dans l'image, pour éviter les
  conflits de dépendances avec Airflow.
- **Contrôle qualité bloquant** avant dbt : une ingestion incomplète ne se
  propage pas jusqu'au rapport.
- **Journal d'exécution** dans BigQuery : volumes de chaque exécution,
  exploitable dans Power BI.
