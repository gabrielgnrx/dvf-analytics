import pandas as pd

from app.donnees import PALETTE, colorer, effet_gare, estimer, evolution, filtrer


def _prix() -> pd.DataFrame:
    return pd.DataFrame({
        "code_commune": ["75101", "75101", "92012", "93001", "75101"],
        "nom_commune": ["Paris 1er", "Paris 1er", "Boulogne", "Aubervilliers", "Paris 1er"],
        "zone": ["Paris", "Paris", "Petite couronne", "Petite couronne", "Paris"],
        "type_bien": ["Appartement"] * 4 + ["Maison"],
        "annee": [2024, 2025, 2025, 2025, 2025],
        "nb_ventes": [100, 120, 80, 40, 6],
        "prix_m2_q1": [11000.0, 11500.0, 7000.0, 3500.0, 9000.0],
        "prix_m2_median": [12500.0, 13000.0, 8000.0, 4000.0, 10000.0],
        "prix_m2_q3": [14000.0, 14500.0, 9000.0, 4500.0, 11000.0],
    })


def test_filtrer():
    vue = filtrer(_prix(), "Appartement", 2025, ["Petite couronne"])
    assert sorted(vue["code_commune"]) == ["92012", "93001"]


def test_colorer_du_moins_cher_au_plus_cher():
    vue = colorer(filtrer(_prix(), "Appartement", 2025, ["Paris", "Petite couronne"]))
    par_commune = dict(zip(vue["code_commune"], vue["couleur"], strict=True))
    assert par_commune["93001"] == PALETTE[0]
    assert par_commune["75101"] == PALETTE[-1]
    assert (vue["rayon"] > 0).all()


def test_colorer_vide():
    assert colorer(_prix().iloc[0:0]).empty


def test_estimer_prend_la_derniere_annee():
    res = estimer(_prix(), "75101", "Appartement", 40)
    assert res["annee"] == 2025
    assert (res["bas"], res["median"], res["haut"]) == (460000, 520000, 580000)


def test_estimer_sans_donnees():
    assert estimer(_prix(), "99999", "Appartement", 40) is None
    assert estimer(_prix(), "75101", "Appartement", 0) is None


def test_evolution_une_colonne_par_commune():
    tab = evolution(_prix(), ["75101", "92012"], "Appartement")
    assert list(tab.index) == [2024, 2025]
    assert tab.loc[2025, "Boulogne"] == 8000


def test_effet_gare():
    gares = pd.DataFrame({
        "zone": ["Paris", "Paris", "Petite couronne"],
        "type_bien": ["Appartement"] * 3,
        "annee": [2025] * 3,
        "tranche_dist_gare": ["1. Moins de 500 m", "2. 500 m à 1 km", "1. Moins de 500 m"],
        "prix_m2_median": [11000.0, 10500.0, 6500.0],
    })
    tab = effet_gare(gares, "Appartement", 2025)
    assert list(tab.index) == ["1. Moins de 500 m", "2. 500 m à 1 km"]
    assert tab.loc["1. Moins de 500 m", "Petite couronne"] == 6500
