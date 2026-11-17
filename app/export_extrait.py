"""Exporte depuis BigQuery l'extrait agrégé qui alimente l'appli Streamlit publique.

L'appli ne se connecte pas à BigQuery : elle lit trois petits fichiers Parquet
versionnés dans app/data/. Ils sont agrégés (commune x type de bien x année),
et les cellules de moins de MIN_VENTES ventes sont retirées, pour ne publier
aucune information rattachable à une vente individuelle.

Usage, après un run complet du pipeline :
    python -m app.export_extrait
"""
from __future__ import annotations

from pathlib import Path

from google.cloud import bigquery

from ingestion.config import config

OUT = Path(__file__).parent / "data"
MIN_VENTES = 5


def _sql(project: str) -> dict[str, str]:
    marts = f"`{project}.analytics_marts"
    return {
        "prix_communes": f"""
            select
              g.code_commune, g.nom_commune, g.code_departement, g.nom_departement, g.zone,
              g.latitude, g.longitude,
              f.type_bien,
              extract(year from f.date_mutation) as annee,
              count(*) as nb_ventes,
              approx_quantiles(f.prix_m2, 4)[offset(1)] as prix_m2_q1,
              approx_quantiles(f.prix_m2, 4)[offset(2)] as prix_m2_median,
              approx_quantiles(f.prix_m2, 4)[offset(3)] as prix_m2_q3,
              approx_quantiles(f.surface_habitable, 2)[offset(1)] as surface_mediane
            from {marts}.fact_transactions` f
            join {marts}.dim_geo` g using (geo_key)
            where f.est_prix_m2_fiable
            group by 1, 2, 3, 4, 5, 6, 7, 8, 9
            having count(*) >= {MIN_VENTES}
        """,
        "prix_gares": f"""
            select
              g.zone,
              f.type_bien,
              extract(year from f.date_mutation) as annee,
              f.tranche_dist_gare,
              count(*) as nb_ventes,
              approx_quantiles(f.prix_m2, 2)[offset(1)] as prix_m2_median
            from {marts}.fact_transactions` f
            join {marts}.dim_geo` g using (geo_key)
            where f.est_prix_m2_fiable and f.tranche_dist_gare is not null
            group by 1, 2, 3, 4
            having count(*) >= {MIN_VENTES}
        """,
        "ecarts_communes": f"""
            select
              g.code_commune, g.nom_commune, g.code_departement, g.zone,
              e.type_bien,
              count(*) as nb_ventes,
              approx_quantiles(abs(e.ecart_pct), 2)[offset(1)] as ecart_absolu_median_pct,
              round(100 * countif(e.ecart_pct <= -20) / count(*), 1) as part_sous_marche_pct,
              round(100 * countif(e.ecart_pct >= 20) / count(*), 1) as part_au_dessus_pct
            from {marts}.mart_ecarts_prix` e
            join {marts}.dim_geo` g using (geo_key)
            group by 1, 2, 3, 4, 5
            having count(*) >= {MIN_VENTES}
        """,
    }


def run() -> None:
    client = bigquery.Client(project=config.project_id, location=config.location)
    OUT.mkdir(parents=True, exist_ok=True)
    for nom, sql in _sql(config.project_id).items():
        df = client.query(sql).to_dataframe()
        chemin = OUT / f"{nom}.parquet"
        df.to_parquet(chemin, index=False)
        print(f"{nom} : {len(df):,} lignes -> {chemin}")


if __name__ == "__main__":
    run()
