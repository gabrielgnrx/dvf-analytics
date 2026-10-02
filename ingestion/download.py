"""Téléchargement des fichiers geo-dvf sur le périmètre configuré.

Les fichiers sont des CSV.gz par (année, département). On les récupère dans
data/raw/ en local avant chargement dans BigQuery.

Détection des changements : pour chaque fichier, on interroge data.gouv (requête
HEAD) et on compare Last-Modified / Content-Length / ETag avec ceux mémorisés au
dernier téléchargement (fichier annexe .meta.json). Le fichier n'est
retéléchargé que si data.gouv l'a republié ; sinon le cache local est réutilisé.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import requests
from tqdm import tqdm

from .config import config

# Surchargeable par variable d'environnement (utile dans un conteneur Airflow).
DATA_DIR = Path(os.getenv("DVF_DATA_DIR", "data/raw"))


_META_KEYS = ("last_modified", "content_length", "etag")


def _remote_meta(url: str) -> dict | None:
    """Métadonnées distantes (HEAD). None si le fichier n'existe pas (404)."""
    resp = requests.head(url, allow_redirects=True, timeout=60)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    h = resp.headers
    return {
        "last_modified": h.get("Last-Modified"),
        "content_length": h.get("Content-Length"),
        "etag": h.get("ETag"),
    }


def _meta_path(dest: Path) -> Path:
    return dest.with_name(dest.name + ".meta.json")


def _read_meta(dest: Path) -> dict | None:
    try:
        return json.loads(_meta_path(dest).read_text())
    except (OSError, ValueError):
        return None


def _is_same(local: dict | None, remote: dict) -> bool:
    if not local:
        return False
    compared = [k for k in _META_KEYS if remote.get(k)]
    return bool(compared) and all(local.get(k) == remote[k] for k in compared)


def download_file(url: str, dest: Path) -> str:
    """Synchronise dest avec url.

    Retourne "absent" (404), "cache" (inchangé), "nouveau" ou "mis à jour".
    """
    try:
        remote = _remote_meta(url)
    except requests.RequestException as exc:
        if dest.exists():
            tqdm.write(f"  (HEAD impossible, cache conservé) {dest.name} : {exc}")
            return "cache"
        raise
    if remote is None:
        return "absent"
    if dest.exists() and _is_same(_read_meta(dest), remote):
        return "cache"

    status = "mis à jour" if dest.exists() else "nouveau"
    resp = requests.get(url, stream=True, timeout=120)
    resp.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with open(tmp, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 16):
            f.write(chunk)
    tmp.replace(dest)
    _meta_path(dest).write_text(json.dumps(remote, indent=2))
    return status


def download_all() -> list[Path]:
    """Synchronise tout le périmètre (année x département). Retourne les chemins."""
    paths: list[Path] = []
    stats: dict[str, int] = {}
    print(f"Années : {', '.join(config.years)} | départements : {', '.join(config.departments)}")
    combos = [(y, d) for y in config.years for d in config.departments]
    for year, dep in tqdm(combos, desc="Téléchargement geo-dvf"):
        dest = DATA_DIR / f"{year}_{dep}.csv.gz"
        status = download_file(config.file_url(year, dep), dest)
        stats[status] = stats.get(status, 0) + 1
        if status == "absent":
            tqdm.write(f"  (absent) {year} dép {dep}")
        else:
            paths.append(dest)
            if status != "cache":
                tqdm.write(f"  ({status}) {year} dép {dep}")
    print("Bilan : " + ", ".join(f"{k} {v}" for k, v in sorted(stats.items())))
    return paths


if __name__ == "__main__":
    downloaded = download_all()
    print(f"\n{len(downloaded)} fichiers disponibles dans {DATA_DIR}/")
