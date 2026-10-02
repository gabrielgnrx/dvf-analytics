"""Pipeline DVF Analytics, orchestré par Airflow.

Ordre d'exécution (une fois par mois) :

    téléchargement geo-dvf
        -> chargement brut BigQuery (raw.dvf_mutations)
        -> contrôle qualité de l'atterrissage (bloquant)
        -> dbt : seeds, staging, intermediate, étoile, avec les tests
           exécutés après chaque modèle (Cosmos : une tâche Airflow par modèle)
        -> entraînement du modèle de prix au m² et écriture des prédictions
        -> dbt : mart des écarts au modèle
        -> journal d'exécution dans BigQuery (analytics_ops.pipeline_runs)

Pourquoi mensuel : DVF est publié deux fois par an, mais le bac à sable
BigQuery fait expirer les tables après 60 jours. Une exécution mensuelle
reconstruit l'entrepôt avant expiration et intègre les nouvelles publications
dès leur sortie.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow.decorators import dag, task
from airflow.exceptions import AirflowFailException
from cosmos import DbtTaskGroup, ExecutionConfig, ProfileConfig, ProjectConfig, RenderConfig
from cosmos.constants import TestBehavior

PROJECT_DIR = os.getenv("DVF_PROJECT_DIR", "/opt/airflow/project")
DBT_DIR = f"{PROJECT_DIR}/dbt/dvf"
GCP_PROJECT = os.getenv("GCP_PROJECT_ID", "")
LOCATION = os.getenv("BQ_LOCATION", "EU")

# Seuils du contrôle d'atterrissage : en dessous, on ne transforme pas.
MIN_RAW_ROWS = 1_000_000
EXPECTED_DEPARTMENTS = {"75", "77", "78", "91", "92", "93", "94", "95"}

PROFILE = ProfileConfig(
    profile_name="dvf",
    target_name="dev",
    profiles_yml_filepath="/opt/airflow/dbt_profiles/profiles.yml",
)
EXECUTION = ExecutionConfig(dbt_executable_path="/opt/airflow/dbt_venv/bin/dbt")
PROJECT = ProjectConfig(dbt_project_path=DBT_DIR)
# emit_datasets=False : évite un conflit connu entre les datasets émis par
# Cosmos et Airflow 2.10 (FlushError sur DatasetModel.aliases).
DBT_ARGS = {"install_deps": True, "emit_datasets": False}

default_args = {
    "owner": "gabriel",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


def _in_project_dir():
    """Les scripts du projet écrivent leurs sorties en chemins relatifs."""
    os.chdir(PROJECT_DIR)


@dag(
    dag_id="dvf_pipeline",
    description="Ingestion DVF, transformation dbt, modèle de prix au m², marts BI",
    schedule="0 6 1 * *",  # le 1er de chaque mois à 6 h
    start_date=datetime(2026, 9, 1),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["dvf", "bigquery", "dbt", "ml"],
    doc_md=__doc__,
)
def dvf_pipeline():

    @task(execution_timeout=timedelta(minutes=30))
    def download_geo_dvf() -> int:
        """Télécharge les fichiers geo-dvf du périmètre (idempotent)."""
        _in_project_dir()
        from ingestion.download import download_all

        paths = download_all()
        if not paths:
            raise AirflowFailException("Aucun fichier geo-dvf disponible.")
        return len(paths)

    @task(execution_timeout=timedelta(minutes=45))
    def load_raw_bigquery(n_files: int) -> None:
        """Recharge raw.dvf_mutations à partir des fichiers téléchargés."""
        _in_project_dir()
        from ingestion.load_to_bq import load

        load()

    @task
    def check_raw_landing() -> dict:
        """Contrôle bloquant : volume minimal et couverture des départements."""
        from google.cloud import bigquery

        client = bigquery.Client(project=GCP_PROJECT, location=LOCATION)
        sql = f"""
            SELECT code_departement, COUNT(*) AS n
            FROM `{GCP_PROJECT}.raw.dvf_mutations`
            GROUP BY code_departement
        """
        rows = {r.code_departement: r.n for r in client.query(sql).result()}
        total = sum(rows.values())
        missing = EXPECTED_DEPARTMENTS - set(rows)
        if total < MIN_RAW_ROWS:
            raise AirflowFailException(f"Volume brut anormal : {total:,} lignes (minimum {MIN_RAW_ROWS:,}).")
        if missing:
            raise AirflowFailException(f"Départements absents du chargement : {sorted(missing)}")
        return {"raw_rows": total, "departements": len(rows)}

    dbt_transform = DbtTaskGroup(
        group_id="dbt_transform",
        project_config=PROJECT,
        profile_config=PROFILE,
        execution_config=EXECUTION,
        render_config=RenderConfig(
            exclude=["mart_ecarts_prix"],
            test_behavior=TestBehavior.AFTER_EACH,
        ),
        operator_args=DBT_ARGS,
    )

    @task(execution_timeout=timedelta(minutes=45))
    def train_price_model() -> None:
        """Réentraîne le modèle et réécrit analytics_ml.predictions_prix_m2."""
        _in_project_dir()
        from ml.train_prix_m2 import run

        run()

    dbt_ml_mart = DbtTaskGroup(
        group_id="dbt_ml_mart",
        project_config=PROJECT,
        profile_config=PROFILE,
        execution_config=EXECUTION,
        render_config=RenderConfig(
            select=["mart_ecarts_prix"],
            test_behavior=TestBehavior.AFTER_EACH,
        ),
        operator_args=DBT_ARGS,
    )

    @task
    def log_run(landing: dict, **context) -> None:
        """Ajoute une ligne de suivi dans analytics_ops.pipeline_runs."""
        import pandas as pd
        from google.cloud import bigquery

        client = bigquery.Client(project=GCP_PROJECT, location=LOCATION)
        counts = {}
        for name, table in {
            "ventes": "analytics_marts.fact_transactions",
            "ventes_scorees": "analytics_marts.mart_ecarts_prix",
        }.items():
            sql = f"SELECT COUNT(*) AS n FROM `{GCP_PROJECT}.{table}`"
            counts[name] = list(client.query(sql).result())[0].n

        ds = bigquery.Dataset(f"{GCP_PROJECT}.analytics_ops")
        ds.location = LOCATION
        client.create_dataset(ds, exists_ok=True)
        row = pd.DataFrame([{
            "run_id": context["run_id"],
            "logical_date": context["logical_date"].isoformat(),
            "finished_at": datetime.utcnow().isoformat(),
            "raw_rows": landing["raw_rows"],
            "departements": landing["departements"],
            "ventes": counts["ventes"],
            "ventes_scorees": counts["ventes_scorees"],
        }])
        client.load_table_from_dataframe(
            row, f"{GCP_PROJECT}.analytics_ops.pipeline_runs",
            job_config=bigquery.LoadJobConfig(write_disposition="WRITE_APPEND"),
        ).result()

    n_files = download_geo_dvf()
    loaded = load_raw_bigquery(n_files)
    landing = check_raw_landing()
    model = train_price_model()

    loaded >> landing >> dbt_transform >> model >> dbt_ml_mart
    dbt_ml_mart >> log_run(landing)


dvf_pipeline()
