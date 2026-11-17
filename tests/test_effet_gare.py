import numpy as np
import pandas as pd
import pytest

from ml.effet_gare import matrice, regression_effet_fixe

TRANCHES = ["1. Moins de 500 m", "2. 500 m à 1 km", "3. 1 à 2 km", "4. Plus de 2 km"]


def _ventes(n_communes: int = 60, ventes_par_commune: int = 80, seed: int = 0) -> pd.DataFrame:
    """Ventes simulées : vrai effet 'moins de 500 m' = +20 %, autres tranches nulles.

    Biais volontaire : les communes chères ont davantage de ventes près des gares,
    comme en petite couronne. Un modèle sans effet commune surestime alors l'effet.
    """
    rng = np.random.default_rng(seed)
    lignes = []
    for c in range(n_communes):
        niveau = rng.normal(8.3, 0.4)  # log du prix de base de la commune
        p_proche = 0.15 + 0.6 * (niveau > 8.3)
        for _ in range(ventes_par_commune):
            proche = rng.random() < p_proche
            tranche = TRANCHES[0] if proche else TRANCHES[int(rng.integers(1, 4))]
            surface = float(rng.uniform(20, 120))
            log_prix = niveau + 0.2 * proche - 0.1 * np.log(surface) + rng.normal(0, 0.15)
            lignes.append({
                "geo_key": f"C{c}", "tranche_dist_gare": tranche, "surface_habitable": surface,
                "nb_pieces": max(1, round(surface / 25)), "type_bien": "Appartement",
                "annee": int(rng.integers(2021, 2026)), "prix_m2": float(np.exp(log_prix)),
            })
    return pd.DataFrame(lignes)


def test_effet_fixe_retrouve_le_vrai_effet():
    df = _ventes()
    X, y = matrice(df)
    res = regression_effet_fixe(X, y, df["geo_key"])
    assert res.loc[TRANCHES[0], "coefficient"] == pytest.approx(0.2, abs=0.03)
    assert abs(res.loc[TRANCHES[1], "coefficient"]) < 0.04
    # l'intervalle de confiance contient la vraie valeur (+22,1 %)
    assert res.loc[TRANCHES[0], "ic95_bas_pct"] < 22.1 < res.loc[TRANCHES[0], "ic95_haut_pct"]


def test_sans_effet_commune_l_estimation_serait_biaisee():
    df = _ventes()
    X, y = matrice(df)
    naif = regression_effet_fixe(X, y, pd.Series("toutes", index=df.index))
    # un seul groupe = simple MCO centré : l'effet gare absorbe l'effet commune
    assert naif.loc[TRANCHES[0], "coefficient"] > 0.3


def test_matrice_exclut_la_reference_et_les_constantes():
    X, y = matrice(_ventes(n_communes=3, ventes_par_commune=20))
    assert "4. Plus de 2 km" not in X.columns
    assert "maison" not in X.columns  # un seul type de bien dans l'échantillon
    assert len(X) == len(y)
