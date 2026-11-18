"""Explorateur public des prix immobiliers en Île-de-France (données DVF).

Lancement local : streamlit run app/streamlit_app.py
Données : extrait agrégé produit par app/export_extrait.py (dossier app/data).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from donnees import colorer, effet_gare, estimer, evolution, filtrer  # noqa: E402

DATA = Path(__file__).parent / "data"
DEPOT = "https://github.com/gabrielgnrx/dvf-analytics"

st.set_page_config(page_title="DVF Analytics, prix immobiliers en Île-de-France", layout="wide")


@st.cache_data
def charger(nom: str) -> pd.DataFrame:
    return pd.read_parquet(DATA / f"{nom}.parquet")


def euros(x: float) -> str:
    return f"{x:,.0f} €".replace(",", " ")


try:
    prix = charger("prix_communes")
    gares = charger("prix_gares")
    ecarts = charger("ecarts_communes")
except FileNotFoundError:
    st.error("Extrait absent : lancer `python -m app.export_extrait` après un run du pipeline.")
    st.stop()

annees = sorted(prix["annee"].unique())
zones = sorted(prix["zone"].dropna().unique())

st.title("Prix immobiliers en Île-de-France")
st.caption(
    f"Ventes notariées DVF {annees[0]} à {annees[-1]}, ventes simples d'un logement. "
    f"Pipeline BigQuery, dbt, LightGBM et Power BI : [code source]({DEPOT})."
)

with st.sidebar:
    type_bien = st.radio("Type de bien", ["Appartement", "Maison"])
    annee = st.select_slider("Année", options=annees, value=annees[-1])
    zones_choisies = st.multiselect("Zones", zones, default=zones)

onglet_carte, onglet_evol, onglet_estim, onglet_gares, onglet_ecarts, onglet_methode = st.tabs(
    ["Carte", "Évolution", "Fourchette de prix", "Effet gare", "Écarts au modèle", "Méthode"]
)

with onglet_carte:
    vue = colorer(filtrer(prix, type_bien, annee, zones_choisies))
    if vue.empty:
        st.info("Aucune commune pour ces filtres.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Communes", f"{len(vue):,}".replace(",", " "))
        c2.metric("Ventes", f"{int(vue['nb_ventes'].sum()):,}".replace(",", " "))
        c3.metric("Prix au m² médian (médiane des communes)", euros(vue["prix_m2_median"].median()))
        st.map(vue, latitude="latitude", longitude="longitude", color="couleur", size="rayon")
        st.caption(
            "Couleur : quintile de prix au m², du vert (moins cher) au rouge. Taille : nombre de ventes."
        )
        cols = ["nom_commune", "nom_departement", "nb_ventes", "prix_m2_q1", "prix_m2_median", "prix_m2_q3"]
        st.dataframe(
            vue.sort_values("prix_m2_median", ascending=False)[cols],
            hide_index=True,
            use_container_width=True,
            column_config={
                "nom_commune": "Commune",
                "nom_departement": "Département",
                "nb_ventes": "Ventes",
                "prix_m2_q1": st.column_config.NumberColumn("1er quartile €/m²", format="%d"),
                "prix_m2_median": st.column_config.NumberColumn("Médiane €/m²", format="%d"),
                "prix_m2_q3": st.column_config.NumberColumn("3e quartile €/m²", format="%d"),
            },
        )

communes = (
    prix[prix["type_bien"] == type_bien]
    .drop_duplicates("code_commune")
    .assign(libelle=lambda d: d["nom_commune"] + " (" + d["code_departement"] + ")")
    .sort_values("libelle")
)
libelles = dict(zip(communes["libelle"], communes["code_commune"], strict=True))

with onglet_evol:
    choix = st.multiselect("Communes à comparer", list(libelles), max_selections=6)
    if choix:
        st.line_chart(evolution(prix, [libelles[c] for c in choix], type_bien), y_label="€/m² médian")
    else:
        st.info("Choisir une ou plusieurs communes.")

with onglet_estim:
    col_a, col_b = st.columns(2)
    commune = col_a.selectbox("Commune", list(libelles))
    surface = col_b.number_input("Surface habitable (m²)", min_value=9, max_value=400, value=50, step=1)
    res = estimer(prix, libelles[commune], type_bien, float(surface)) if commune else None
    if res is None:
        st.info("Pas assez de ventes comparables pour cette commune.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Bas de fourchette", euros(res["bas"]))
        c2.metric("Prix médian", euros(res["median"]))
        c3.metric("Haut de fourchette", euros(res["haut"]))
        st.caption(
            f"Repère statistique, pas une estimation : la moitié des {res['nb_ventes']} ventes de "
            f"{type_bien.lower()}s de la commune en {res['annee']} se situent dans cette fourchette "
            f"(prix au m² médian {euros(res['prix_m2_median'])}). L'étage, l'état et le DPE du bien "
            "ne sont pas dans DVF."
        )

with onglet_gares:
    tableau = effet_gare(gares, type_bien, annee)
    st.bar_chart(tableau, stack=False, y_label="€/m² médian")
    st.caption(
        "Prix au m² médian selon la distance à la gare la plus proche (gares IDFM en service). "
        "Lecture descriptive : les gares sont plus denses dans les secteurs chers, l'écart ne mesure "
        "pas à lui seul l'effet de la gare."
    )

with onglet_ecarts:
    min_ventes = st.slider("Ventes minimum par commune", 5, 200, 30, step=5)
    vue = ecarts[
        (ecarts["type_bien"] == type_bien)
        & ecarts["zone"].isin(zones_choisies)
        & (ecarts["nb_ventes"] >= min_ventes)
    ]
    st.markdown(
        "Écart entre le prix de vente et le prix attendu par le modèle LightGBM, calculé hors "
        "échantillon. Un écart médian élevé signale un marché hétérogène, que la localisation et "
        "la surface expliquent mal."
    )
    st.dataframe(
        vue.sort_values("ecart_absolu_median_pct", ascending=False)[
            ["nom_commune", "zone", "nb_ventes", "ecart_absolu_median_pct",
             "part_sous_marche_pct", "part_au_dessus_pct"]
        ],
        hide_index=True,
        use_container_width=True,
        column_config={
            "nom_commune": "Commune",
            "zone": "Zone",
            "nb_ventes": "Ventes",
            "ecart_absolu_median_pct": st.column_config.NumberColumn("Écart médian %", format="%.1f"),
            "part_sous_marche_pct": st.column_config.NumberColumn("Sous le marché (< -20 %)", format="%.1f"),
            "part_au_dessus_pct": st.column_config.NumberColumn("Au-dessus (> 20 %)", format="%.1f"),
        },
    )

with onglet_methode:
    st.markdown(
        f"""
- **Source** : Demandes de valeurs foncières géolocalisées (data.gouv.fr), Île-de-France.
- **Périmètre** : ventes d'un seul logement de 9 m² ou plus, prix au m² entre 1 000 et 30 000 €.
- **Confidentialité** : chiffres agrégés par commune, type de bien et année ; les groupes de
  moins de 5 ventes ne sont pas publiés.
- **Chaîne** : ingestion Python vers BigQuery, transformation et tests dbt, modèle LightGBM,
  orchestration Airflow, rapport Power BI. Détails et code : [{DEPOT}]({DEPOT}).
"""
    )
