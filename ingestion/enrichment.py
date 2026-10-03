"""Sources d'enrichissement : données ouvertes croisées avec DVF.

Quatre sources, chargées telles quelles dans le dataset brut BigQuery (raw) ;
le nettoyage et les calculs (distances, parts) se font dans dbt :

  - raw.ref_gares            gares et stations en service (métro, RER, train,
                             tram), Île-de-France Mobilités ;
  - raw.ref_gares_projet     gares et stations en projet, dont celles du
                             Grand Paris Express (lignes 15 à 18), IDFM ;
  - raw.ref_revenus_communes revenus disponibles par commune (INSEE Filosofi,
                             via data.gouv) ;
  - raw.ref_dpe_communes     nombre de DPE par commune et par étiquette
                             énergétique (ADEME, DPE des logements existants).

Les volumes sont faibles (quelques milliers de lignes) : chaque table est
rechargée en entier à chaque exécution (WRITE_TRUNCATE), ce qui la tient à jour
sans logique de détection de changements.

Usage : python -m ingestion.enrichment
"""
from __future__ import annotations

import io
import re
import unicodedata

import pandas as pd
import requests
from google.cloud import bigquery

from .config import config

IDFM = "https://data.iledefrance-mobilites.fr/api/explore/v2.1/catalog/datasets"
GARES_URL = f"{IDFM}/emplacement-des-gares-idf/exports/csv"
PROJETS_URL = f"{IDFM}/projets_arrets_idf/exports/csv"
REVENUS_DATASET = "https://www.data.gouv.fr/api/1/datasets/revenu-des-francais-a-la-commune/"
DPE_AGG_URL = "https://data.ademe.fr/data-fair/api/v1/datasets/dpe03existant/values_agg"

TIMEOUT = 120


def _get(url: str, **params) -> requests.Response:
    resp = requests.get(url, params=params or None, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp


def _norm(s: str) -> str:
    """Nom de colonne sans accents ni ponctuation, pour des correspondances robustes."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _split_point(df: pd.DataFrame, col: str = "geo_point_2d") -> pd.DataFrame:
    """'48.85, 2.35' -> colonnes latitude / longitude (texte, typées en staging)."""
    parts = df[col].fillna("").str.split(",", n=1, expand=True)
    df["latitude"] = parts[0].str.strip()
    df["longitude"] = parts[1].str.strip() if parts.shape[1] > 1 else None
    return df


def fetch_gares() -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(_get(GARES_URL).text), sep=";", dtype=str)
    df = _split_point(df)
    keep = ["id_gares", "nom_gares", "mode", "res_com", "indice_lig", "exploitant",
            "principal", "latitude", "longitude"]
    return df[[c for c in keep if c in df.columns]]


def fetch_gares_projet() -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(_get(PROJETS_URL).text), sep=";", dtype=str)
    df = _split_point(df)
    keep = ["nom_arret", "id_projet", "nom_projet", "mode", "sous_mode", "indice",
            "phase", "statut", "creation", "cor_exist", "latitude", "longitude"]
    return df[[c for c in keep if c in df.columns]]


def _revenus_csv_url() -> str:
    """URL du CSV le plus récent du jeu data.gouv (elle change à chaque republication)."""
    meta = _get(REVENUS_DATASET).json()
    csvs = [r for r in meta["resources"] if (r.get("format") or "").lower() == "csv"]
    if not csvs:
        raise RuntimeError("Aucune ressource CSV dans le jeu revenus data.gouv")
    return max(csvs, key=lambda r: r.get("last_modified") or "")["url"]


# Colonnes retenues (revenu disponible "[DISP]"), repérées par mots-clés car les
# libellés INSEE contiennent des caractères spéciaux instables.
REVENUS_COLS = {
    "code_commune": ("code geographique",),
    "libelle_commune": ("libelle geographique",),
    "nb_menages": ("disp", "nbre de menages fiscaux"),
    "revenu_median": ("disp", "mediane"),
    "revenu_d1": ("disp", "1er decile"),
    "revenu_d9": ("disp", "9e decile"),
    "part_pensions_pct": ("disp", "part des pensions"),
}


def fetch_revenus() -> pd.DataFrame:
    url = _revenus_csv_url()
    raw = pd.read_csv(io.StringIO(_get(url).content.decode("utf-8-sig")), sep=";", dtype=str)
    out = {}
    for target, keys in REVENUS_COLS.items():
        match = [c for c in raw.columns if all(k in _norm(c) for k in keys)]
        if not match:
            raise RuntimeError(f"Colonne introuvable pour {target} ({keys})")
        out[target] = raw[match[0]]
    df = pd.DataFrame(out)
    df = df[df["code_commune"].str[:2].isin(config.departments)]
    df["millesime"] = re.search(r"(20\d\d)", url).group(1) if re.search(r"(20\d\d)", url) else None
    df["source_url"] = url
    return df


def fetch_dpe() -> pd.DataFrame:
    """Nombre de DPE par commune et étiquette, agrégé côté API ADEME (un appel par département)."""
    rows = []
    for dep in config.departments:
        data = _get(
            DPE_AGG_URL,
            field="code_insee_ban;etiquette_dpe",
            agg_size=1000,
            size=0,
            qs=f"code_departement_ban:{dep}",
        ).json()
        for commune in data["aggs"]:
            for etiq in commune.get("aggs", []):
                rows.append({
                    "code_commune": str(commune["value"]),
                    "etiquette_dpe": str(etiq["value"]),
                    "nb_dpe": int(etiq["total"]),
                })
    return pd.DataFrame(rows)


SOURCES = {
    "ref_gares": fetch_gares,
    "ref_gares_projet": fetch_gares_projet,
    "ref_revenus_communes": fetch_revenus,
    "ref_dpe_communes": fetch_dpe,
}


def load_all() -> dict[str, int]:
    client = bigquery.Client(project=config.project_id, location=config.location)
    ds = bigquery.Dataset(f"{config.project_id}.{config.raw_dataset}")
    ds.location = config.location
    client.create_dataset(ds, exists_ok=True)

    counts = {}
    for table, fetch in SOURCES.items():
        df = fetch()
        if df.empty:
            raise RuntimeError(f"Source vide : {table}")
        df["_loaded_at"] = pd.Timestamp.utcnow().isoformat()
        fqn = f"{config.project_id}.{config.raw_dataset}.{table}"
        client.load_table_from_dataframe(
            df, fqn,
            job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE"),
        ).result()
        counts[table] = len(df)
        print(f"{table:<22} {len(df):>7,} lignes")
    return counts


if __name__ == "__main__":
    load_all()
