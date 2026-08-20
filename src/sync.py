"""Sincroniza los registros de mantenimiento/inspección desde Datascope
hacia la base de datos local (SQLite) o Supabase (Postgres), según .env.

Uso:
    python -m src.sync
"""
import sys
from datetime import datetime, timezone

from src import config, db, datascope_client

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


def main():
    print(f"Conectando a Datascope (form_id={config.DATASCOPE_FORM_ID})...")
    registros = datascope_client.fetch_normalized_registros()
    print(f"  {len(registros)} registros obtenidos.")

    engine = db.init_db()
    db.upsert_registros(engine, registros, synced_at=datetime.now(timezone.utc))
    print(f"Sincronización completa -> {config.get_database_url()}")


if __name__ == "__main__":
    main()
