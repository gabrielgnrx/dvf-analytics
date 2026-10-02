"""Configuration centrale de l'ingestion, lue depuis l'environnement (.env)."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from functools import cached_property

import requests

from dotenv import load_dotenv

load_dotenv()

# URL des fichiers geo-dvf (DVF géolocalisé, déjà enrichi lat/lon).
# Structure : .../{year}/departements/{dep}.csv.gz
GEO_DVF_BASE = "https://files.data.gouv.fr/geo-dvf/latest/csv"


# Repli si data.gouv est injoignable lors de la découverte des années.
FALLBACK_YEARS = ["2021", "2022", "2023", "2024", "2025"]


def discover_years(timeout: int = 30) -> list[str]:
    """Lit sur data.gouv la liste des millésimes publiés dans geo-dvf/latest.

    Le jeu "latest" couvre une fenêtre glissante d'environ 5 ans : quand
    data.gouv ajoute une année (ou en retire une ancienne), le pipeline suit
    automatiquement sans modification de configuration.
    """
    resp = requests.get(f"{GEO_DVF_BASE}/", timeout=timeout)
    resp.raise_for_status()
    years = sorted(set(re.findall(r'href="(?:[^"]*/)?(\d{4})/"', resp.text)))
    if not years:
        raise RuntimeError("Aucune année trouvée dans l'index geo-dvf")
    return years


def _split_env(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [v.strip() for v in raw.split(",") if v.strip()]


@dataclass
class Config:
    project_id: str = field(default_factory=lambda: os.environ["GCP_PROJECT_ID"])
    location: str = field(default_factory=lambda: os.getenv("BQ_LOCATION", "EU"))
    raw_dataset: str = field(default_factory=lambda: os.getenv("BQ_RAW_DATASET", "raw"))
    raw_table: str = "dvf_mutations"
    # "auto" (défaut) = années découvertes sur data.gouv ; sinon liste "2023,2024".
    years_setting: str = field(default_factory=lambda: os.getenv("DVF_YEARS", "auto"))
    departments: list[str] = field(
        default_factory=lambda: _split_env(
            "DVF_DEPARTMENTS", "75,77,78,91,92,93,94,95"
        )
    )

    @cached_property
    def years(self) -> list[str]:
        if self.years_setting.strip().lower() != "auto":
            return [v.strip() for v in self.years_setting.split(",") if v.strip()]
        try:
            return discover_years()
        except Exception as exc:  # réseau, format de page inattendu...
            print(f"[config] découverte des années impossible ({exc}), repli {FALLBACK_YEARS}")
            return FALLBACK_YEARS

    @property
    def raw_table_fqn(self) -> str:
        return f"{self.project_id}.{self.raw_dataset}.{self.raw_table}"

    def file_url(self, year: str, dep: str) -> str:
        return f"{GEO_DVF_BASE}/{year}/departements/{dep}.csv.gz"


config = Config()
