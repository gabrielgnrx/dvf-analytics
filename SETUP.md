# SETUP

Deux façons d'exécuter la chaîne. Aucune ne nécessite de clé de service account.

## Option A (utilisée) : Google Cloud Shell

Cloud Shell est une VM Linux gratuite, déjà authentifiée sur le compte Google,
avec accès Internet. C'est l'environnement d'exécution du projet.

1. Projet GCP : `data-510311` (mode bac à sable BigQuery, sans facturation).
   Limite du bac à sable : les tables expirent au bout de 60 jours. La chaîne
   étant entièrement reproductible, il suffit de la relancer.
2. Datasets créés en région `EU` :

   ```bash
   bq --location=EU mk -d data-510311:raw
   bq --location=EU mk -d data-510311:analytics
   ```

3. Environnement :

   ```bash
   cd ~/dvf-analytics
   cp .env.example .env            # puis GCP_PROJECT_ID=data-510311
   echo 'export GCP_PROJECT_ID=data-510311' >> ~/.bashrc
   python3 -m venv .venv && . .venv/bin/activate
   pip install -r requirements.txt
   mkdir -p ~/.dbt && cp dbt/dvf/profiles.yml.example ~/.dbt/profiles.yml
   ```

   Le profil dbt utilise `method: oauth` : il réutilise les identifiants de la
   session Cloud Shell.

## Option B : poste local

Mêmes étapes, avec en plus le SDK Google Cloud installé puis :

```bash
gcloud auth application-default login
```

dbt et le client Python BigQuery utilisent alors ces identifiants (OAuth).
La cible dbt `sa` (service account + clé JSON) reste disponible pour une CI.

## Ordre d'exécution complet

```bash
python -m ingestion.load_to_bq       # télécharge geo-dvf et remplit raw.dvf_mutations
python -m exploration.profiling      # rapport de profilage de la donnée brute
cd dbt/dvf && dbt deps && dbt build  # seeds + staging + intermediate + marts + tests
```

Périmètre (`.env`) : `DVF_YEARS=2021,2022,2023,2024,2025` (geo-dvf « latest »
couvre les 5 dernières années, 2025 partielle) et les 8 départements d'Île-de-France.
