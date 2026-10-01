"""Configuration centrale de l'ingestion, lue depuis l'environnement (.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()

# URL des fichiers geo-dvf (DVF géolocalisé, déjà enrichi lat/lon).
# Structure : .../{year}/departements/{dep}.csv.gz
GEO_DVF_BASE = "https://files.data.gouv.fr/geo-dvf/latest/csv"


def _split_env(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [v.strip() for v in raw.split(",") if v.strip()]


@dataclass
class Config:
    project_id: str = field(default_factory=lambda: os.environ["GCP_PROJECT_ID"])
    location: str = field(default_factory=lambda: os.getenv("BQ_LOCATION", "EU"))
    raw_dataset: str = field(default_factory=lambda: os.getenv("BQ_RAW_DATASET", "raw"))
    raw_table: str = "dvf_mutations"
    years: list[str] = field(
        default_factory=lambda: _split_env("DVF_YEARS", "2021,2022,2023,2024,2025")
    )
    departments: list[str] = field(
        default_factory=lambda: _split_env(
            "DVF_DEPARTMENTS", "75,77,78,91,92,93,94,95"
        )
    )

    @property
    def raw_table_fqn(self) -> str:
        return f"{self.project_id}.{self.raw_dataset}.{self.raw_table}"

    def file_url(self, year: str, dep: str) -> str:
        return f"{GEO_DVF_BASE}/{year}/departements/{dep}.csv.gz"


config = Config()
