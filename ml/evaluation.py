"""Fonctions d'évaluation du modèle prix au m², sans dépendance à BigQuery ni à LightGBM.

Séparées du script d'entraînement pour être testées unitairement (tests/).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score


class Regresseur(Protocol):
    def predict(self, X: pd.DataFrame) -> np.ndarray: ...


FitFn = Callable[[pd.DataFrame, pd.Series], Regresseur]


def metrics(y_true_m2: np.ndarray, y_pred_m2: np.ndarray) -> dict[str, float]:
    """Métriques en €/m² (MAE), en erreur relative (MdAPE, part à ±10 %) et R² sur le log."""
    ape = np.abs(y_pred_m2 - y_true_m2) / y_true_m2
    return {
        "MAE (€/m²)": round(mean_absolute_error(y_true_m2, y_pred_m2), 0),
        "MdAPE (%)": round(float(np.median(ape)) * 100, 1),
        "Part à ±10 % (%)": round(float(np.mean(ape <= 0.10)) * 100, 1),
        "R² (log)": round(r2_score(np.log(y_true_m2), np.log(y_pred_m2)), 3),
    }


def baseline(train: pd.DataFrame, other: pd.DataFrame) -> np.ndarray:
    """Médiane commune x type sur l'entraînement, repli sur le département puis sur l'ensemble."""
    by_ct = train.groupby(["code_commune", "type_bien"], observed=True)["prix_m2"].median()
    by_d = train.groupby(["code_departement", "type_bien"], observed=True)["prix_m2"].median()
    keys_ct = list(zip(other["code_commune"], other["type_bien"], strict=True))
    keys_d = list(zip(other["code_departement"], other["type_bien"], strict=True))
    pred = pd.Series(keys_ct, dtype=object).map(by_ct.to_dict())
    fallback = pd.Series(keys_d, dtype=object).map(by_d.to_dict())
    return pred.fillna(fallback).fillna(train["prix_m2"].median()).to_numpy(dtype=float)


def segment_errors(df: pd.DataFrame, pred_col: str, by: str) -> pd.DataFrame:
    """Erreur relative médiane par segment, segments les plus difficiles en premier."""
    ape = (df[pred_col] - df["prix_m2"]).abs() / df["prix_m2"]
    return (
        df.assign(ape=ape)
        .groupby(by, observed=True)
        .agg(
            n=("ape", "size"),
            prix_m2_median=("prix_m2", "median"),
            MdAPE_pct=("ape", lambda s: round(s.median() * 100, 1)),
        )
        .sort_values("MdAPE_pct", ascending=False)
        .reset_index()
    )


def predictions_hors_echantillon(
    df: pd.DataFrame,
    feats: list[str],
    fit_fn: FitFn,
    groupe: str = "annee",
    cible: str = "y",
) -> np.ndarray:
    """Prédit chaque vente avec un modèle qui ne l'a jamais vue (une année exclue à la fois).

    Pour chaque année A : entraînement sur toutes les autres années, prédiction
    des ventes de A. Chaque vente reçoit donc une prédiction hors échantillon.

    Pourquoi : l'écart entre prix réel et prix "attendu" n'a de sens que si le
    modèle n'a pas appris la vente elle-même. Prédire les données
    d'entraînement donne des écarts artificiellement tassés (le modèle colle en
    partie à ce qu'il a vu) et sous-estime les ventes atypiques.

    La cible est en log : la fonction renvoie exp(prédiction), en €/m².
    """
    groupes = sorted(df[groupe].unique())
    if len(groupes) < 2:
        raise ValueError(f"Au moins deux valeurs de '{groupe}' sont nécessaires, trouvé {groupes}.")
    pred = np.full(len(df), np.nan)
    for g in groupes:
        masque = (df[groupe] == g).to_numpy(dtype=bool)
        modele = fit_fn(df.loc[~masque, feats], df.loc[~masque, cible])
        pred[masque] = modele.predict(df.loc[masque, feats])
    return np.exp(pred)


def ecart_pct(prix_m2: np.ndarray, prix_m2_predit: np.ndarray) -> np.ndarray:
    """Écart du prix réel au prix attendu, en % du prix attendu (positif = vendu au-dessus)."""
    return np.round((prix_m2 - prix_m2_predit) / prix_m2_predit * 100, 1)
