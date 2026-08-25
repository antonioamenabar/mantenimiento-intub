"""Copia los datos de la base SQLite local al Postgres configurado en
DATABASE_URL (Supabase), dentro del esquema `config.DB_SCHEMA`. Pensado
para correrse UNA vez al pasar de desarrollo local a la nube -- es seguro
correrlo de nuevo (si una tabla ya tiene filas en destino, la salta en vez
de duplicar).

Uso:
    python -m scripts.migrar_a_postgres
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from sqlalchemy import create_engine, text

from src import db, config

# Orden solo por prolijidad en el log -- no hay FKs declaradas que exijan
# un orden estricto de inserción.
TABLAS_EN_ORDEN = [
    "flota", "item_catalogo", "reglas_mantencion", "componentes_camion",
    "mantenimiento_registros", "faenas_registros", "tickets", "fallas_historico",
    "eventos_mantenimiento", "usuarios", "mecanicos_talleres",
    "ordenes_trabajo", "ot_items", "ot_item_sistema", "ot_item_fotos",
    "inspeccion_checklist_catalogo", "inspeccion_checklist_respuestas",
]

# SQLite guarda los booleanos como 0/1 (entero); Postgres sí tiene un tipo
# boolean real y no acepta un entero ahí sin casteo explícito -- hay que
# convertir estas columnas antes de copiar.
COLUMNAS_BOOLEANAS = {
    "flota": ["activo"],
    "usuarios": ["activo"],
    "mecanicos_talleres": ["activo"],
    "componentes_camion": ["tiene_horometro_propio"],
    "mantenimiento_registros": ["finished"],
}


def migrar():
    if config.DB_BACKEND != "postgres":
        raise RuntimeError("DB_BACKEND debe ser 'postgres' en .env antes de migrar.")

    sqlite_engine = create_engine(f"sqlite:///{config.SQLITE_PATH}")
    pg_engine = db.init_db()  # asegura que el esquema y las tablas existan

    print(f"Migrando de {config.SQLITE_PATH} al esquema '{config.DB_SCHEMA}' en Postgres...\n")

    for tabla in TABLAS_EN_ORDEN:
        try:
            df = pd.read_sql(f"SELECT * FROM {tabla}", sqlite_engine)
        except Exception as exc:  # noqa: BLE001 -- tabla vieja que no existe en sqlite, se sigue
            print(f"  {tabla}: no existe en sqlite local, se salta ({exc})")
            continue

        if df.empty:
            print(f"  {tabla}: 0 filas en origen, nada que copiar")
            continue

        for columna in COLUMNAS_BOOLEANAS.get(tabla, []):
            if columna in df.columns:
                df[columna] = df[columna].astype("boolean")  # nullable, preserva NaN si hay

        with pg_engine.connect() as conn:
            existentes = conn.execute(text(f"SELECT count(*) FROM {config.DB_SCHEMA}.{tabla}")).scalar()

        if existentes:
            print(f"  {tabla}: destino ya tiene {existentes} fila(s), se salta (para no duplicar)")
            continue

        df.to_sql(tabla, pg_engine, schema=config.DB_SCHEMA, if_exists="append", index=False)
        print(f"  {tabla}: {len(df)} fila(s) copiada(s)")

    print("\nMigración terminada.")


if __name__ == "__main__":
    migrar()
