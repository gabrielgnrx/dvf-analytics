"""Calculs de l'appli Streamlit, séparés de l'interface pour être testés."""
from __future__ import annotations

import pandas as pd

# Dégradé du moins cher au plus cher (hexadécimal avec transparence, pour st.map).
PALETTE = ["#228B22AA", "#9ACD32AA", "#FFC800AA", "#FF7800AA", "#C81E1EAA"]


def filtrer(prix: pd.DataFrame, type_bien: str, annee: int, zones: list[str]) -> pd.DataFrame:
    """Communes d'un type de bien et d'une année, dans les zones choisies."""
    masque = (prix["type_bien"] == type_bien) & (prix["annee"] == annee) & prix["zone"].isin(zones)
    return prix.loc[masque].copy()


def colorer(df: pd.DataFrame, colonne: str = "prix_m2_median") -> pd.DataFrame:
    """Ajoute une couleur par quintile de prix (colonne 'couleur') et un rayon selon le volume."""
    out = df.copy()
    if out.empty:
        out["couleur"] = []
        out["rayon"] = []
        return out
    n_classes = min(len(PALETTE), out[colonne].nunique())
    if n_classes < 2:
        classes = pd.Series(0, index=out.index)
    else:
        classes = pd.qcut(out[colonne].rank(method="first"), n_classes, labels=False)
    out["couleur"] = [PALETTE[int(c * (len(PALETTE) - 1) / max(n_classes - 1, 1))] for c in classes]
    out["rayon"] = 150 + 40 * out["nb_ventes"].clip(upper=400) ** 0.5
    return out


def estimer(prix: pd.DataFrame, code_commune: str, type_bien: str, surface: float) -> dict | None:
    """Fourchette indicative : surface x quartiles du prix au m² de la dernière année disponible.

    Repère statistique simple (pas le modèle LightGBM) : la moitié des ventes
    comparables de la commune se situent dans la fourchette.
    """
    sel = prix[(prix["code_commune"] == code_commune) & (prix["type_bien"] == type_bien)]
    if sel.empty or surface <= 0:
        return None
    derniere = sel.loc[sel["annee"].idxmax()]
    return {
        "annee": int(derniere["annee"]),
        "nb_ventes": int(derniere["nb_ventes"]),
        "bas": round(surface * derniere["prix_m2_q1"], -3),
        "median": round(surface * derniere["prix_m2_median"], -3),
        "haut": round(surface * derniere["prix_m2_q3"], -3),
        "prix_m2_median": float(derniere["prix_m2_median"]),
    }


def evolution(prix: pd.DataFrame, codes_communes: list[str], type_bien: str) -> pd.DataFrame:
    """Prix au m² médian par année (lignes) et par commune (colonnes)."""
    sel = prix[prix["code_commune"].isin(codes_communes) & (prix["type_bien"] == type_bien)]
    return sel.pivot_table(index="annee", columns="nom_commune", values="prix_m2_median").sort_index()


def effet_gare(gares: pd.DataFrame, type_bien: str, annee: int) -> pd.DataFrame:
    """Prix au m² médian par tranche de distance à la gare (lignes) et par zone (colonnes)."""
    sel = gares[(gares["type_bien"] == type_bien) & (gares["annee"] == annee)]
    return sel.pivot_table(index="tranche_dist_gare", columns="zone", values="prix_m2_median").sort_index()
