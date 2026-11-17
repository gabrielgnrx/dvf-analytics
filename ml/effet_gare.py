"""Effet propre de la proximité d'une gare sur le prix au m² (régression hédonique).

Le tableau descriptif de docs/enrichissement.md compare des communes
différentes : en petite couronne, les ventes proches d'une gare sont aussi
plus proches de Paris. Ici on compare des ventes de la MÊME commune : effet
fixe commune, à surface, nombre de pièces, type de bien et année égaux.

    log(prix_m2) = effet commune + tranche de distance à la gare
                   + log(surface) + pièces + maison + année + erreur

L'effet fixe est absorbé en centrant chaque variable par commune
(théorème de Frisch-Waugh-Lovell). Erreurs standard robustes, groupées par
commune (les ventes d'une même commune ne sont pas indépendantes).

Usage : python -m ml.effet_gare
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

REFERENCE = "4. Plus de 2 km"
OUT = Path(os.getenv("ML_OUTPUT_DIR", "ml/output"))


def matrice(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, str]:
    """Variables explicatives (indicatrices, référence exclue), cible log(prix_m2) et tranche de référence.

    La référence est la tranche « plus de 2 km » quand elle existe, sinon la tranche la plus
    éloignée présente (à Paris, aucune vente n'est à plus de 2 km d'une gare). Sans référence,
    les indicatrices de tranche seraient colinéaires avec l'effet fixe commune.
    """
    presentes = sorted(df["tranche_dist_gare"].unique())
    reference = REFERENCE if REFERENCE in presentes else presentes[-1]
    tranches = pd.get_dummies(df["tranche_dist_gare"], dtype=float).drop(columns=reference)
    annees = pd.get_dummies(df["annee"].astype(str), prefix="annee", dtype=float).iloc[:, 1:]
    X = pd.concat(
        [
            tranches,
            pd.DataFrame(
                {
                    "log_surface": np.log(df["surface_habitable"].astype(float)),
                    "nb_pieces": df["nb_pieces"].astype(float),
                    "maison": (df["type_bien"] == "Maison").astype(float),
                },
                index=df.index,
            ),
            annees,
        ],
        axis=1,
    )
    # Variables constantes dans l'échantillon (ex. un seul type de bien) : retirées.
    X = X.loc[:, X.std() > 0]
    return X, np.log(df["prix_m2"].astype(float)), reference


def regression_effet_fixe(X: pd.DataFrame, y: pd.Series, groupes: pd.Series) -> pd.DataFrame:
    """MCO avec effet fixe par groupe et erreurs standard groupées. Une ligne par variable."""
    Xc = X - X.groupby(groupes.to_numpy()).transform("mean")
    yc = y - y.groupby(groupes.to_numpy()).transform("mean")
    A, b = Xc.to_numpy(), yc.to_numpy()
    beta, *_ = np.linalg.lstsq(A, b, rcond=None)
    residus = b - A @ beta

    bread = np.linalg.pinv(A.T @ A)
    codes, uniques = pd.factorize(groupes)
    scores = np.zeros((len(uniques), A.shape[1]))
    np.add.at(scores, codes, A * residus[:, None])
    meat = scores.T @ scores
    n, k, g = len(b), A.shape[1] + len(uniques), len(uniques)
    # Erreurs groupées : non définies avec un seul groupe.
    correction = g / (g - 1) * (n - 1) / max(n - k, 1) if g > 1 else np.nan
    se = np.sqrt(np.diag(bread @ meat @ bread) * correction)

    return pd.DataFrame(
        {
            "coefficient": beta,
            "erreur_standard": se,
            "effet_pct": (np.exp(beta) - 1) * 100,
            "ic95_bas_pct": (np.exp(beta - 1.96 * se) - 1) * 100,
            "ic95_haut_pct": (np.exp(beta + 1.96 * se) - 1) * 100,
        },
        index=X.columns,
    )


SQL = """
select f.prix_m2, f.surface_habitable, f.nb_pieces, f.type_bien, f.tranche_dist_gare,
       extract(year from f.date_mutation) as annee, f.geo_key, g.zone
from `{project}.analytics_marts.fact_transactions` f
join `{project}.analytics_marts.dim_geo` g using (geo_key)
where f.est_prix_m2_fiable and f.tranche_dist_gare is not null and f.nb_pieces > 0
"""


def run() -> None:
    from google.cloud import bigquery

    from ingestion.config import config

    client = bigquery.Client(project=config.project_id, location=config.location)
    df = client.query(SQL.format(project=config.project_id)).to_dataframe()

    lignes = ["# Effet de la proximité d'une gare, à commune égale\n",
              "Écart de prix au m² avec les ventes de la tranche de référence de la même commune "
              "(plus de 2 km d'une gare, ou tranche la plus éloignée disponible). "
              "Contrôles : surface (log), pièces, maison, année. IC à 95 %, erreurs groupées par commune.\n"]
    for zone in ["Paris", "Petite couronne", "Grande couronne"]:
        for type_bien in ["Appartement", "Maison"]:
            part = df[(df["zone"] == zone) & (df["type_bien"] == type_bien)]
            if part["tranche_dist_gare"].nunique() < 2 or part["geo_key"].nunique() < 2:
                continue
            X, y, reference = matrice(part)
            res = regression_effet_fixe(X, y, part["geo_key"])
            tranches = res.loc[[c for c in res.index if c[:1].isdigit()]].round(1)
            titre = f"{zone}, {type_bien.lower()}s ({len(part):,} ventes, référence : {reference[3:]})"
            lignes += [f"\n## {titre}\n",
                       tranches[["effet_pct", "ic95_bas_pct", "ic95_haut_pct"]].to_markdown()]
            print(f"{zone}, {type_bien} :\n{tranches.to_string()}\n")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "effet_gare.md").write_text("\n".join(lignes), encoding="utf-8")
    print(f"Rapport écrit dans {OUT / 'effet_gare.md'}")


if __name__ == "__main__":
    run()
