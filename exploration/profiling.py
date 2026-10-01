"""Profilage de la donnée brute raw.dvf_mutations.

Produit un rapport (console + Markdown) des problèmes de qualité à traiter en
staging. Cette sortie alimente directement le rapport de gouvernance du projet.

Points surveillés spécifiques à DVF :
  - taux de nuls par colonne clé
  - valeurs foncières nulles, nulles-ou-zéro, aberrantes
  - mutations multi-lots (nombre_lots > 1) qui faussent le prix au m²
  - surfaces bâties à 0 ou absurdes
  - répartition par type_local et par département
"""
from __future__ import annotations

from pathlib import Path

from google.cloud import bigquery

from ingestion.config import config

OUT = Path("exploration/output")

QUERIES: dict[str, str] = {
    "volumétrie": """
        SELECT code_departement, COUNT(*) AS n
        FROM `{t}`
        GROUP BY code_departement
        ORDER BY code_departement
    """,
    "taux_nuls_valeur_fonciere": """
        SELECT
          COUNTIF(valeur_fonciere IS NULL OR valeur_fonciere = '') AS nuls,
          COUNT(*) AS total,
          ROUND(COUNTIF(valeur_fonciere IS NULL OR valeur_fonciere = '')
                / COUNT(*) * 100, 2) AS pct_nuls
        FROM `{t}`
    """,
    "mutations_multi_lots": """
        SELECT
          SAFE_CAST(nombre_lots AS INT64) AS nb_lots,
          COUNT(*) AS n
        FROM `{t}`
        GROUP BY nb_lots
        ORDER BY nb_lots
    """,
    "repartition_type_local": """
        SELECT COALESCE(type_local, '(nul)') AS type_local, COUNT(*) AS n
        FROM `{t}`
        GROUP BY type_local
        ORDER BY n DESC
    """,
    "surfaces_suspectes": """
        SELECT
          COUNTIF(SAFE_CAST(surface_reelle_bati AS FLOAT64) = 0) AS surface_zero,
          COUNTIF(SAFE_CAST(surface_reelle_bati AS FLOAT64) > 1000) AS surface_gt_1000,
          COUNTIF(SAFE_CAST(valeur_fonciere AS FLOAT64) < 1000) AS valeur_lt_1000,
          COUNTIF(SAFE_CAST(valeur_fonciere AS FLOAT64) > 20000000) AS valeur_gt_20m
        FROM `{t}`
    """,
}


def run() -> None:
    client = bigquery.Client(project=config.project_id, location=config.location)
    OUT.mkdir(parents=True, exist_ok=True)
    report = ["# Rapport de profilage — raw.dvf_mutations\n"]

    for name, sql in QUERIES.items():
        df = client.query(sql.format(t=config.raw_table_fqn)).to_dataframe()
        print(f"\n=== {name} ===")
        print(df.to_string(index=False))
        report.append(f"## {name}\n")
        report.append(df.to_markdown(index=False))
        report.append("\n")

    (OUT / "profiling_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"\nRapport écrit dans {OUT / 'profiling_report.md'}")


if __name__ == "__main__":
    run()
