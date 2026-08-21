"""Carga inicial (o actualización) del maestro de flota desde data/flota_inicial.csv.

Uso:
    python -m src.seed_flota
"""
import csv
import sys
from pathlib import Path

from src import config, db

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

CSV_PATH = config.ROOT_DIR / "data" / "flota_inicial.csv"


def load_csv() -> tuple[list[dict], list[dict]]:
    validos, sin_patente = [], []
    with open(CSV_PATH, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            patente = (row.get("patente") or "").strip()
            orden_raw = (row.get("orden") or "").strip()
            registro = {
                "patente": patente,
                "alias": row.get("alias", "").strip(),
                "familia": row.get("familia", "").strip() or None,
                "orden": int(orden_raw) if orden_raw else None,
                "nombre_corto": row.get("nombre_corto", "").strip() or None,
                "activo": row.get("activo", "true").strip().lower() == "true",
            }
            if patente:
                validos.append(registro)
            else:
                sin_patente.append(registro)
    return validos, sin_patente


def main():
    engine = db.init_db()
    validos, sin_patente = load_csv()
    db.upsert_flota(engine, validos)
    print(f"Flota cargada: {len(validos)} camiones con patente.")
    if sin_patente:
        print(f"\n⚠️  {len(sin_patente)} camiones SIN patente confirmada (no se cargaron):")
        for r in sin_patente:
            print(f"   - {r['alias']}")
        print("   Complétalos en data/flota_inicial.csv y vuelve a correr este script.")


if __name__ == "__main__":
    main()
