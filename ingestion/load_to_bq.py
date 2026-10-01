"""Chargement des fichiers geo-dvf dans la table brute BigQuery raw.dvf_mutations.

Principe : atterrissage fidèle de la donnée, AUCUN nettoyage ici. Tout est chargé
en STRING pour ne rien perdre ni casser sur des valeurs sales. Le typage et le
nettoyage se font dans la couche staging dbt, où ils sont versionnés et testés.

La table est recréée à chaque exécution complète (WRITE_TRUNCATE) pour rester
idempotent et reproductible.
"""
from __future__ import annotations

import gzip
import io

import pandas as pd
from google.cloud import bigquery
from tqdm import tqdm

from .config import config
from .download import download_all

# Colonnes du schéma geo-dvf qu'on conserve. On garde large : le tri se fera en staging.
GEO_DVF_COLUMNS = [
    "id_mutation",
    "date_mutation",
    "nature_mutation",
    "valeur_fonciere",
    "adresse_numero",
    "adresse_nom_voie",
    "code_postal",
    "code_commune",
    "nom_commune",
    "code_departement",
    "id_parcelle",
    "nombre_lots",
    "code_type_local",
    "type_local",
    "surface_reelle_bati",
    "nombre_pieces_principales",
    "surface_terrain",
    "longitude",
    "latitude",
]


def ensure_dataset(client: bigquery.Client) -> None:
    ds_id = f"{config.project_id}.{config.raw_dataset}"
    dataset = bigquery.Dataset(ds_id)
    dataset.location = config.location
    client.create_dataset(dataset, exists_ok=True)


def read_file(path) -> pd.DataFrame:
    """Lit un CSV.gz geo-dvf en forçant tout en STRING (atterrissage brut)."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        df = pd.read_csv(
            io.StringIO(f.read()),
            dtype=str,
            usecols=lambda c: c in GEO_DVF_COLUMNS,
            low_memory=False,
        )
    # Colonnes manquantes éventuelles -> présentes et vides, schéma stable.
    for col in GEO_DVF_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    df["_source_file"] = str(path.name)
    df["_loaded_at"] = pd.Timestamp.utcnow().isoformat()
    return df[GEO_DVF_COLUMNS + ["_source_file", "_loaded_at"]]


def load() -> None:
    client = bigquery.Client(project=config.project_id, location=config.location)
    ensure_dataset(client)

    paths = download_all()
    if not paths:
        raise SystemExit("Aucun fichier à charger. Vérifier le périmètre dans .env")

    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        source_format=bigquery.SourceFormat.PARQUET,
        schema=[bigquery.SchemaField(c, "STRING") for c in GEO_DVF_COLUMNS]
        + [
            bigquery.SchemaField("_source_file", "STRING"),
            bigquery.SchemaField("_loaded_at", "STRING"),
        ],
    )

    first = True
    for path in tqdm(paths, desc="Chargement BigQuery"):
        df = read_file(path)
        job_config.write_disposition = (
            bigquery.WriteDisposition.WRITE_TRUNCATE
            if first
            else bigquery.WriteDisposition.WRITE_APPEND
        )
        job = client.load_table_from_dataframe(
            df, config.raw_table_fqn, job_config=job_config
        )
        job.result()
        first = False

    table = client.get_table(config.raw_table_fqn)
    print(f"\nChargé : {table.num_rows:,} lignes dans {config.raw_table_fqn}")


if __name__ == "__main__":
    load()
