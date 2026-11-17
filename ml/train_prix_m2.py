"""Modèle de prédiction du prix au m² (ventes simples d'un logement, IDF).

Méthodologie :
  - Cible : log(prix_m2). Le log stabilise la variance (Paris vs grande
    couronne) et rend l'erreur relative, plus parlante métier.
  - Découpage TEMPOREL, pas aléatoire, relatif aux données disponibles :
    test = année la plus récente (jamais vue), validation = année précédente
    (réglage, early stopping), entraînement = toutes les années antérieures.
    Avec les millésimes 2021-2025 : entraînement 2021-2023, validation 2024,
    test 2025. Quand data.gouv publie une nouvelle année, la fenêtre glisse
    toute seule. C'est la situation
    réelle d'usage : prédire des ventes futures à partir du passé. Un split
    aléatoire surestimerait la performance (fuite d'information temporelle).
  - Référence (baseline) : prix médian au m² de la commune x type de bien
    sur la période d'entraînement. Le modèle doit faire mieux que cette règle
    simple, sinon il n'apporte rien.
  - Modèle : LightGBM (gradient boosting), robuste aux non-linéarités et aux
    interactions surface x localisation.
  - Variables d'enrichissement (données ouvertes) : accessibilité en
    transports (distance à la gare la plus proche, nombre de gares à 1 km,
    distance à la future gare du Grand Paris Express), revenu médian et
    inégalités de la commune (INSEE), part de passoires thermiques (ADEME).
    Le modèle est aussi entraîné sans elles pour mesurer leur apport.
  - Analyse d'erreur par département et par type de bien, importance des
    variables.
  - Écarts au marché pour le BI : chaque vente est prédite par un modèle
    entraîné sans son année (une année exclue à la fois). Les écarts sont donc
    calculés hors échantillon : un modèle qui prédirait ses propres données
    d'entraînement donnerait des écarts artificiellement tassés.

Usage : python -m ml.train_prix_m2
"""
from __future__ import annotations

import os
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from google.cloud import bigquery

from ingestion.config import config
from ml.evaluation import (
    baseline,
    ecart_pct,
    metrics,
    predictions_hors_echantillon,
    segment_errors,
)

OUT = Path(os.getenv("ML_OUTPUT_DIR", "ml/output"))
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
  f.dist_gare_m,
  f.nb_gares_1km,
  f.dist_gpe_m,
  g.revenu_median_uc,
  g.rapport_d9_d1,
  g.part_dpe_fg_pct,
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
# Variables issues des sources d'enrichissement (LightGBM gère les valeurs nulles).
ENRICH = [
    "dist_gare_m", "nb_gares_1km", "dist_gpe_m",
    "revenu_median_uc", "rapport_d9_d1", "part_dpe_fg_pct",
]
PARAMS = {
    "n_estimators": 3000, "learning_rate": 0.05, "num_leaves": 127,
    "min_child_samples": 40, "subsample": 0.8, "subsample_freq": 1,
    "colsample_bytree": 0.8, "reg_lambda": 1.0, "verbose": -1,
}


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


def fit(train: pd.DataFrame, valid: pd.DataFrame, feats: list[str]) -> lgb.LGBMRegressor:
    model = lgb.LGBMRegressor(**PARAMS)
    model.fit(
        train[feats], train["y"],
        eval_set=[(valid[feats], valid["y"])],
        callbacks=[lgb.early_stopping(100, verbose=False)],
    )
    return model


def run() -> None:
    client = bigquery.Client(project=config.project_id, location=config.location)
    df = load(client)
    print(f"{len(df):,} ventes exploitables")

    annee_test = int(df["annee"].max())
    annee_valid = annee_test - 1
    train = df[df["annee"] < annee_valid]
    valid = df[df["annee"] == annee_valid]
    test = df[df["annee"] == annee_test]
    print(f"split : train <= {annee_valid - 1} | valid {annee_valid} | test {annee_test}")
    print(f"train {len(train):,} | valid {len(valid):,} | test {len(test):,}")

    # Modèle sans enrichissement : référence pour mesurer l'apport des sources externes.
    feats_base = CAT + NUM
    model_base = fit(train, valid, feats_base)

    feats = CAT + NUM + ENRICH
    model = fit(train, valid, feats)
    print(f"meilleure itération : {model.best_iteration_}")

    results = {}
    for name, part in [(f"validation {annee_valid}", valid), (f"test {annee_test}", test)]:
        if part.empty:
            continue
        pred = np.exp(model.predict(part[feats]))
        results[f"Modèle enrichi — {name}"] = metrics(part["prix_m2"].to_numpy(), pred)
        pred_base = np.exp(model_base.predict(part[feats_base]))
        results[f"Modèle sans enrichissement — {name}"] = metrics(part["prix_m2"].to_numpy(), pred_base)
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

    # Écarts au marché pour le BI : prédictions hors échantillon (une année
    # exclue à la fois), au nombre d'itérations retenu par l'early stopping.
    params_finaux = {**model.get_params(), "n_estimators": model.best_iteration_}

    def fit_annee(X: pd.DataFrame, y: pd.Series) -> lgb.LGBMRegressor:
        return lgb.LGBMRegressor(**params_finaux).fit(X, y)

    df["prix_m2_predit"] = predictions_hors_echantillon(df, feats, fit_annee).round(0)
    df["ecart_pct"] = ecart_pct(df["prix_m2"].to_numpy(), df["prix_m2_predit"].to_numpy())
    oof = metrics(df["prix_m2"].to_numpy(), df["prix_m2_predit"].to_numpy())
    print(f"prédictions hors échantillon : {oof}")
    out = df[["transaction_id", "prix_m2_predit", "ecart_pct"]].copy()

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
        (
            f"Ventes exploitables : {len(df):,} (train {len(train):,}, "
            f"validation {len(valid):,}, test {len(test):,}).\n"
        ),
        "## Performance (modèle enrichi, modèle sans enrichissement, baseline médiane commune x type)\n",
        res.to_markdown(),
        "\n## Erreur par département (jeu de test)\n",
        err_dep.to_markdown(index=False),
        "\n## Erreur par type de bien (jeu de test)\n",
        err_type.to_markdown(index=False),
        "\n## Importance des variables (gain)\n",
        imp.to_markdown(index=False),
        "\n## Prédictions hors échantillon (écarts au marché du BI)\n",
        "Chaque vente prédite par un modèle entraîné sans son année.\n",
        pd.DataFrame([oof], index=["Toutes années"]).to_markdown(),
    ]
    (OUT / "rapport_modele.md").write_text("\n".join(report), encoding="utf-8")
    print((OUT / "rapport_modele.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    run()
