"""Configuration centralisée : variables d'environnement, à défaut le fichier .env."""
import os
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]


def _charger_dotenv() -> None:
    fichier = RACINE / ".env"
    if not fichier.exists():
        return
    for ligne in fichier.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, valeur = ligne.split("=", 1)
        os.environ.setdefault(cle.strip(), valeur.strip())


_charger_dotenv()

# --- Data lake (RustFS, API S3) ---
RUSTFS_ENDPOINT = os.getenv("RUSTFS_ENDPOINT", "http://localhost:9100")
RUSTFS_ACCESS_KEY = os.getenv("RUSTFS_ACCESS_KEY", "rustfsadmin")
RUSTFS_SECRET_KEY = os.getenv("RUSTFS_SECRET_KEY", "rustfsadmin")
LAKE_BUCKET = os.getenv("LAKE_BUCKET", "panier-vert")

# --- PostgreSQL ---
PG_HOST = os.getenv("POSTGRES_HOST", "localhost")
PG_PORT = os.getenv("POSTGRES_PORT", "5440")
PG_DB = os.getenv("POSTGRES_DB", "panier_vert")
PG_USER = os.getenv("POSTGRES_USER", "panier")
PG_PASSWORD = os.getenv("POSTGRES_PASSWORD", "panier")
PG_URL = f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"

# --- Données locales ---
DATA_DIR = RACINE / "data"