# Image Airflow du projet DVF Analytics.
# - Airflow 2.10 (image officielle) + Astronomer Cosmos pour piloter dbt
# - dbt-bigquery isolé dans son propre environnement virtuel (recommandation
#   Cosmos : évite les conflits de dépendances entre Airflow et dbt)
FROM apache/airflow:2.10.5-python3.11

USER root
# libgomp1 : runtime OpenMP requis par LightGBM
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 \
 && apt-get clean && rm -rf /var/lib/apt/lists/*
USER airflow

COPY --chmod=644 requirements-airflow.txt /tmp/requirements-airflow.txt
RUN pip install --no-cache-dir -r /tmp/requirements-airflow.txt

RUN python -m venv /opt/airflow/dbt_venv \
 && /opt/airflow/dbt_venv/bin/pip install --no-cache-dir "dbt-bigquery==1.8.2"
