"""Téléchargement des fichiers geo-dvf sur le périmètre configuré.

Les fichiers sont des CSV.gz par (année, département). On les récupère dans
data/raw/ en local avant chargement dans BigQuery. Idempotent : un fichier déjà
présent n'est pas retéléchargé.
"""
from __future__ import annotations

import os
from pathlib import Path

import requests
from tqdm import tqdm

from .config import config

# Surchargeable par variable d'environnement (utile dans un conteneur Airflow).
DATA_DIR = Path(os.getenv("DVF_DATA_DIR", "data/raw"))


def download_file(url: str, dest: Path) -> bool:
    """Télécharge url vers dest. Retourne False si la source n'existe pas (404)."""
    if dest.exists():
        return True
    resp = requests.get(url, stream=True, timeout=120)
    if resp.status_code == 404:
        # Certains (année, département) peuvent manquer : on ignore proprement.
        return False
    resp.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with open(tmp, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 16):
            f.write(chunk)
    tmp.rename(dest)
    return True


def download_all() -> list[Path]:
    """Télécharge tout le périmètre (année x département). Retourne les chemins."""
    paths: list[Path] = []
    combos = [(y, d) for y in config.years for d in config.departments]
    for year, dep in tqdm(combos, desc="Téléchargement geo-dvf"):
        dest = DATA_DIR / f"{year}_{dep}.csv.gz"
        ok = download_file(config.file_url(year, dep), dest)
        if ok:
            paths.append(dest)
        else:
            tqdm.write(f"  (absent) {year} dép {dep}")
    return paths


if __name__ == "__main__":
    downloaded = download_all()
    print(f"\n{len(downloaded)} fichiers disponibles dans {DATA_DIR}/")
