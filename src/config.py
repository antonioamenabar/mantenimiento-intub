"""Configuración del proyecto, cargada desde variables de entorno (.env)."""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

DATASCOPE_API_KEY = os.getenv("DATASCOPE_API_KEY", "")
DATASCOPE_FORM_ID = int(os.getenv("DATASCOPE_FORM_ID", "658357"))

DB_BACKEND = os.getenv("DB_BACKEND", "sqlite")
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Ruta del archivo SQLite local (solo se usa si DB_BACKEND=sqlite)
SQLITE_PATH = ROOT_DIR / "data" / "mantenimiento.db"


def get_database_url() -> str:
    """Devuelve la URL de conexión según el backend configurado."""
    if DB_BACKEND == "postgres":
        if not DATABASE_URL:
            raise RuntimeError(
                "DB_BACKEND=postgres pero falta DATABASE_URL en .env "
                "(Supabase > Settings > Database > Connection string)"
            )
        return DATABASE_URL
    # sqlite por default
    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{SQLITE_PATH}"
