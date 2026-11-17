import numpy as np
import pandas as pd
import pytest

from ml.evaluation import (
    baseline,
    ecart_pct,
    metrics,
    predictions_hors_echantillon,
    segment_errors,
)


def test_metrics_prediction_parfaite():
    y = np.array([3000.0, 5000.0, 10000.0])
    m = metrics(y, y)
    assert m["MAE (€/m²)"] == 0
    assert m["MdAPE (%)"] == 0
    assert m["Part à ±10 % (%)"] == 100
    assert m["R² (log)"] == 1


def test_metrics_erreur_relative():
    y = np.array([1000.0, 1000.0, 1000.0, 1000.0])
    pred = np.array([1050.0, 1200.0, 900.0, 1000.0])  # 5 %, 20 %, 10 %, 0 %
    m = metrics(y, pred)
    assert m["MdAPE (%)"] == 7.5
    assert m["Part à ±10 % (%)"] == 75


def test_baseline_replis_successifs():
    train = pd.DataFrame({
        "code_commune": ["A", "A", "B"],
        "code_departement": ["75", "75", "92"],
        "type_bien": ["Appartement", "Appartement", "Maison"],
        "prix_m2": [10000.0, 12000.0, 6000.0],
    })
    other = pd.DataFrame({
        "code_commune": ["A", "C", "Z"],
        "code_departement": ["75", "92", "93"],
        "type_bien": ["Appartement", "Maison", "Maison"],
    })
    # commune connue -> médiane commune ; commune inconnue -> département ;
    # département inconnu -> médiane globale
    np.testing.assert_allclose(baseline(train, other), [11000.0, 6000.0, 10000.0])


def test_segment_errors_trie_du_plus_difficile():
    df = pd.DataFrame({
        "dep": ["75", "75", "93"],
        "prix_m2": [100.0, 100.0, 100.0],
        "pred": [110.0, 90.0, 150.0],
    })
    res = segment_errors(df, "pred", "dep")
    assert list(res["dep"]) == ["93", "75"]
    assert list(res["MdAPE_pct"]) == [50.0, 10.0]
    assert list(res["n"]) == [1, 2]


class _ModeleMoyenne:
    def __init__(self, valeur: float):
        self.valeur = valeur

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return np.full(len(X), self.valeur)


def test_hors_echantillon_aucune_vente_vue_a_l_entrainement():
    df = pd.DataFrame({
        "annee": [2021, 2021, 2022, 2022, 2023],
        "x": [1.0, 2.0, 3.0, 4.0, 5.0],
        "y": np.log([1000.0, 1000.0, 2000.0, 2000.0, 4000.0]),
    })
    annees_vues: list[set[int]] = []

    def fit(X: pd.DataFrame, y: pd.Series) -> _ModeleMoyenne:
        annees_vues.append(set(df.loc[X.index, "annee"]))
        return _ModeleMoyenne(float(y.mean()))

    pred = predictions_hors_echantillon(df, ["x"], fit)

    # un modèle par année, chacun entraîné sans l'année qu'il prédit
    assert annees_vues == [{2022, 2023}, {2021, 2023}, {2021, 2022}]
    assert not np.isnan(pred).any()
    # 2023 prédite avec la moyenne des logs de 2021-2022 : exp(mean) en €/m²
    attendu_2023 = np.exp(np.log([1000.0, 1000.0, 2000.0, 2000.0]).mean())
    assert pred[4] == pytest.approx(attendu_2023)


def test_hors_echantillon_annee_entiere_nullable():
    # extract(year ...) arrive de BigQuery en Int64 (entier nullable pandas)
    df = pd.DataFrame({
        "annee": pd.array([2021, 2022, 2022], dtype="Int64"),
        "x": [1.0, 2.0, 3.0],
        "y": np.log([1000.0, 2000.0, 2000.0]),
    })
    pred = predictions_hors_echantillon(df, ["x"], lambda X, y: _ModeleMoyenne(float(y.mean())))
    np.testing.assert_allclose(pred, [2000.0, 1000.0, 1000.0])


def test_hors_echantillon_exige_deux_annees():
    df = pd.DataFrame({"annee": [2024, 2024], "x": [1.0, 2.0], "y": [0.0, 0.0]})
    with pytest.raises(ValueError):
        predictions_hors_echantillon(df, ["x"], lambda X, y: _ModeleMoyenne(0.0))


def test_ecart_pct_signe():
    np.testing.assert_allclose(
        ecart_pct(np.array([1100.0, 900.0]), np.array([1000.0, 1000.0])), [10.0, -10.0]
    )
