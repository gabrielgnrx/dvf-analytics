# Appli publique (Streamlit)

Explorateur des prix au m² par commune, évolution, fourchette de prix, effet
gare et écarts au modèle. L'appli ne se connecte pas à BigQuery : elle lit un
extrait agrégé versionné dans `app/data/`.

## Mettre à jour l'extrait

Après un run complet du pipeline (Airflow ou à la main) :

```powershell
python -m app.export_extrait
git add app/data
git commit -m "Appli : extrait de données mis à jour"
git push
```

L'extrait ne contient que des agrégats commune x type de bien x année ; les
groupes de moins de 5 ventes sont retirés.

## Lancer en local

```powershell
pip install -r app/requirements.txt
streamlit run app/streamlit_app.py
```

## Publier (Streamlit Community Cloud, gratuit)

1. share.streamlit.io, connexion avec le compte GitHub.
2. Create app > dépôt `gabrielgnrx/dvf-analytics`, branche `main`,
   fichier `app/streamlit_app.py`.
3. Advanced settings : Python 3.11. Deploy.

L'appli se met à jour à chaque push sur `main`.
