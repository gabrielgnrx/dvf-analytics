# DVF Analytics — End-to-end real estate analytics platform

[![CI](https://github.com/gabrielgnrx/dvf-analytics/actions/workflows/ci.yml/badge.svg)](https://github.com/gabrielgnrx/dvf-analytics/actions/workflows/ci.yml)
[![dbt docs](https://github.com/gabrielgnrx/dvf-analytics/actions/workflows/dbt-docs.yml/badge.svg)](https://gabrielgnrx.github.io/dvf-analytics/)

*Version française : [README.md](README.md). Code comments and documentation are in French.*

Analytics platform built on France's open property transaction records (DVF,
geocoded edition, published by the tax administration on data.gouv.fr). It
covers the full chain from cloud ingestion to BI reporting, with a data
science layer and a data quality layer.

Scope: Île-de-France (Paris region, 8 départements), all years currently
published (rolling window of about five years, discovered at each run).

**Public app (price map, price ranges, station effect, model residuals; in French):** https://dvf-analytics.streamlit.app/

**dbt documentation (lineage, descriptions, tests):** https://gabrielgnrx.github.io/dvf-analytics/

## Stack

| Layer | Folder | What it shows |
|---|---|---|
| Ingestion | `ingestion/` | Python pipeline to BigQuery, only re-downloads files that were republished |
| Enrichment | `ingestion/enrichment.py` | Open data joins: train stations and future Grand Paris Express stations (IDFM), household income (INSEE), energy ratings (ADEME); geospatial distances computed in BigQuery |
| Transformation | `dbt/dvf/` | Staging, intermediate and star schema (fact + time, geography, property dimensions), tests, exposures, source freshness |
| Data science | `ml/` | LightGBM price per m² model with time-based validation and a business baseline; out-of-sample predictions; hedonic regression with municipality fixed effects |
| BI | `bi/` | Power BI project (PBIP): star schema, DAX measures, row-level security, 5-page report |
| Orchestration | `airflow/` | Monthly Airflow DAG (Docker, Astronomer Cosmos), blocking data quality gate, run log |
| Public app | `app/` | Streamlit explorer on an aggregated extract (no group under 5 sales) |
| Engineering | `.github/workflows/`, `tests/` | CI (ruff, pytest, dbt parse), dbt docs on GitHub Pages, pre-commit |

## Key points

- **Getting the grain right.** A DVF sale is split across several rows and the
  sale price is repeated on each one. The `int_dvf__mutations` model brings
  data back to one row per sale before any price per m² is computed.
- **Flag, don't delete.** Price per m² is only computed for single-dwelling
  sales, and a `est_prix_m2_fiable` flag (1,000 to 30,000 €/m²) keeps
  outliers visible in the BI layer instead of silently dropping them.
- **Honest model evaluation.** Training on the oldest years, early stopping on
  the next one, testing on the most recent year never seen. LightGBM beats the
  municipality x property type median baseline (13.0% vs 16.3% median absolute
  percentage error on 2025, run of 3 October 2026).
- **Out-of-sample residuals.** The "sold above / below market" analysis uses
  predictions from models that never saw the sale (leave-one-year-out), so
  residuals are not shrunk by the model memorising its training data
  (12.2% median absolute percentage error across all sales).
- **Correlation vs. effect.** Flats within 500 m of a station sell about 80%
  higher per m² in the inner suburbs, but stations cluster in expensive
  municipalities. `ml/effet_gare.py` estimates the effect within the same
  municipality, with clustered standard errors: the premium drops to about 23%
  (95% CI 7% to 41%).

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # requirements-dev.txt for tests
cp .env.example .env                     # set GCP_PROJECT_ID
python -m ingestion.load_to_bq && python -m ingestion.enrichment
cd dbt/dvf && dbt deps && dbt build && cd ../..
python -m ml.train_prix_m2
```

Full setup in `SETUP.md`, orchestration in `airflow/README.md`, public app in
`app/README.md`.

## License

Code under the MIT license. Data remains under its producers' licenses.
