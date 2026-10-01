"""Modèle de prédiction du prix au m² (ventes simples d'un logement, IDF).

Méthodologie :
  - Cible : log(prix_m2). Le log stabilise la variance (Paris vs grande
    couronne) et rend l'erreur relative, plus parlante métier.
  - Découpage TEMPOREL, pas aléatoire : entraînement 2021-2023, validation
    2024 (réglage, early stopping), test 2025 (jamais vu). C'est la situation
    réelle d'usage : prédire des ventes futures à partir du passé. Un split
    aléatoire surestimerait la performance (fuite d'information temporelle).
  - Référence (baseline) : prix médian au m² de la commune x type de bien
    sur la période d'entraînement. Le modèle doit faire mieux que cette règle
    simple, sinon il n'apporte rien.
  - Modèle : LightGBM (gradient boosting), robuste aux non-linéarités et aux
    interactions surface x localisation.
  - Analyse d'erreur par département et par type de bien, importance des
    variables, puis réinjection des prédictions dans BigQuery pour le BI.

Usage : python -m ml.train_prix_m2
"""
from __future__ import annotations

from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from google.cloud import bigquery
from sklearn.metrics import mean_absolute_error, r2_score

from ingestion.config import config

OUT = Path("ml/output")
FACT = "analytics_marts.fact_transactions"
GEO = "analytics_marts.dim_geo"
PRED_TABLE = "analytics_ml.predictions_prix_m2"

SQL = f"""
select
  f.transaction_id,
  f.date_mutation,
  extract(year from f.date_mutation)    as annee,
  extract(month from f.date_mutation)   as mois,
  f.code_departement,
  f.geo_key                             as code_commune,
  f.type_bien,
  f.surface_habitable,
  f.nb_pieces,
  coalesce(f.surface_terrain, 0)        as surface_terrain,
  f.nb_dependances,
  f.latitude,
  f.longitude,
  g.latitude                            as commune_lat,
  g.longitude                           as commune_lon,
  f.prix_m2
from `{config.project_id}.{FACT}` f
join `{config.project_id}.{GEO}` g using (geo_key)
where f.est_prix_m2_fiable
"""

CAT = ["code_departement", "code_commune", "type_bien"]
NUM = [
    "surface_habitable", "nb_pieces", "surface_terrain", "nb_dependances",
    "latitude", "longitude", "commune_lat", "commune_lon", "mois", "t",
]


def load(client: bigquery.Client) -> pd.DataFrame:
    df = client.query(SQL).to_dataframe()
    df["date_mutation"] = pd.to_datetime(df["date_mutation"])
    # Temps continu en années depuis 2021 : capte la tendance de marché.
    df["t"] = (df["date_mutation"] - pd.Timestamp("2021-01-01")).dt.days / 365.25
    # Coordonnées manquantes : on retombe sur le centroïde de la commune.
    df["latitude"] = df["latitude"].fillna(df["commune_lat"])
    df["longitude"] = df["longitude"].fillna(df["commune_lon"])
    for c in CAT:
        df[c] = df[c].astype("category")
    df["y"] = np.log(df["prix_m2"])
    return df


def metrics(y_true_m2: np.ndarray, y_pred_m2: np.ndarray) -> dict[str, float]:
    ape = np.abs(y_pred_m2 - y_true_m2) / y_true_m2
    return {
        "MAE (€/m²)": round(mean_absolute_error(y_true_m2, y_pred_m2), 0),
        "MdAPE (%)": round(float(np.median(ape)) * 100, 1),
        "Part à ±10 % (%)": round(float(np.mean(ape <= 0.10)) * 100, 1),
        "R² (log)": round(r2_score(np.log(y_true_m2), np.log(y_pred_m2)), 3),
    }


def baseline(train: pd.DataFrame, other: pd.DataFrame) -> np.ndarray:
    """Médiane commune x type sur l'entraînement, repli sur le département."""
    by_ct = train.groupby(["code_commune", "type_bien"], observed=True)["prix_m2"].median()
    by_d = train.groupby(["code_departement", "type_bien"], observed=True)["prix_m2"].median()
    keys_ct = list(zip(other["code_commune"], other["type_bien"]))
    keys_d = list(zip(other["code_departement"], other["type_bien"]))
    pred = pd.Series(keys_ct).map(by_ct.to_dict())
    fallback = pd.Series(keys_d).map(by_d.to_dict())
    return pred.fillna(fallback).fillna(train["prix_m2"].median()).to_numpy()


def segment_errors(df: pd.DataFrame, pred_col: str, by: str) -> pd.DataFrame:
    ape = (df[pred_col] - df["prix_m2"]).abs() / df["prix_m2"]
    return (
        df.assign(ape=ape)
        .groupby(by, observed=True)
        .agg(n=("ape", "size"), prix_m2_median=("prix_m2", "median"),
             MdAPE_pct=("ape", lambda s: round(s.median() * 100, 1)))
        .sort_values("MdAPE_pct", ascending=False)
        .reset_index()
    )


def run() -> None:
    client = bigquery.Client(project=config.project_id, location=config.location)
    df = load(client)
    print(f"{len(df):,} ventes exploitables")

    train = df[df["annee"] <= 2023]
    valid = df[df["annee"] == 2024]
    test = df[df["annee"] >= 2025]
    print(f"train {len(train):,} | valid {len(valid):,} | test {len(test):,}")

    feats = CAT + NUM
    model = lgb.LGBMRegressor(
        n_estimators=3000, learning_rate=0.05, num_leaves=127,
        min_child_samples=40, subsample=0.8, subsample_freq=1,
        colsample_bytree=0.8, reg_lambda=1.0, verbose=-1,
    )
    model.fit(
        train[feats], train["y"],
        eval_set=[(valid[feats], valid["y"])],
        callbacks=[lgb.early_stopping(100, verbose=False)],
    )
    print(f"meilleure itération : {model.best_iteration_}")

    results = {}
    for name, part in [("validation 2024", valid), ("test 2025", test)]:
        if part.empty:
            continue
        pred = np.exp(model.predict(part[feats]))
        results[f"Modèle — {name}"] = metrics(part["prix_m2"].to_numpy(), pred)
        results[f"Baseline — {name}"] = metrics(part["prix_m2"].to_numpy(), baseline(train, part))
    res = pd.DataFrame(results).T
    print(res.to_string())

    eval_part = test if not test.empty else valid
    eval_part = eval_part.assign(pred=np.exp(model.predict(eval_part[feats])))
    err_dep = segment_errors(eval_part, "pred", "code_departement")
    err_type = segment_errors(eval_part, "pred", "type_bien")

    imp = (
        pd.DataFrame({"variable": feats,
                      "importance_gain": model.booster_.feature_importance("gain")})
        .assign(part_pct=lambda d: (d.importance_gain / d.importance_gain.sum() * 100).round(1))
        .sort_values("part_pct", ascending=False)[["variable", "part_pct"]]
    )

    # Réentraînement sur tout l'historique au nombre d'itérations retenu,
    # puis prédiction de toutes les ventes pour le BI (écart prix réel / modèle).
    final = lgb.LGBMRegressor(**{**model.get_params(), "n_estimators": model.best_iteration_})
    final.fit(df[feats], df["y"])
    df["prix_m2_predit"] = np.exp(final.predict(df[feats])).round(0)
    out = df[["transaction_id", "prix_m2_predit"]].copy()
    out["ecart_pct"] = ((df["prix_m2"] - df["prix_m2_predit"]) / df["prix_m2_predit"] * 100).round(1)

    ds = bigquery.Dataset(f"{config.project_id}.analytics_ml")
    ds.location = config.location
    client.create_dataset(ds, exists_ok=True)
    client.load_table_from_dataframe(
        out, f"{config.project_id}.{PRED_TABLE}",
        job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE"),
    ).result()
    print(f"{len(out):,} prédictions écrites dans {PRED_TABLE}")

    OUT.mkdir(parents=True, exist_ok=True)
    report = [
        "# Modèle prix au m² — rapport d'évaluation\n",
        f"Ventes exploitables : {len(df):,} (train {len(train):,}, "
        f"validation {len(valid):,}, test {len(test):,}).\n",
        "## Performance (modèle vs baseline médiane commune x type)\n",
        res.to_markdown(),
        "\n## Erreur par département (jeu de test)\n",
        err_dep.to_markdown(index=False),
        "\n## Erreur par type de bien (jeu de test)\n",
        err_type.to_markdown(index=False),
        "\n## Importance des variables (gain)\n",
        imp.to_markdown(index=False),
    ]
    (OUT / "rapport_modele.md").write_text("\n".join(report), encoding="utf-8")
    print((OUT / "rapport_modele.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    run()
