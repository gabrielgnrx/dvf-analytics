import os
import sys
from pathlib import Path

# Racine du projet importable (ingestion, ml) et configuration sans réseau ni GCP.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("GCP_PROJECT_ID", "projet-test")
os.environ.setdefault("DVF_YEARS", "2024,2025")
