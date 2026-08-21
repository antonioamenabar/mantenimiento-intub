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
    engine = db.init_db()
    ahora = datetime.now(timezone.utc)

    print(f"Conectando a Datascope (form_id={config.DATASCOPE_FORM_ID})...")
    registros = datascope_client.fetch_normalized_registros()
    print(f"  {len(registros)} registros obtenidos.")
    db.upsert_registros(engine, registros, synced_at=ahora)

    print(f"Conectando a Datascope (Reporte Faenas en Terreno, form_ids={datascope_client.FAENAS_FORM_IDS})...")
    faenas = datascope_client.fetch_normalized_faenas()
    print(f"  {len(faenas)} registros obtenidos.")
    db.upsert_faenas(engine, faenas, synced_at=ahora)

    print("Conectando a Datascope (Tickets / findings, no cerrados, últimos ~6 meses)...")
    tickets = datascope_client.fetch_normalized_tickets_no_cerrados()
    print(f"  {len(tickets)} tickets obtenidos.")
    db.replace_tickets(engine, tickets, synced_at=ahora)

    print(f"Sincronización completa -> {config.get_database_url()}")


if __name__ == "__main__":
    main()
