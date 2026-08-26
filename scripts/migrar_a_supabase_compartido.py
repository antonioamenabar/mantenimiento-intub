"""Migra los datos REALES (no de prueba) desde el Supabase personal
provisorio hacia el esquema `mantenimiento` del Supabase compartido de la
empresa (el proyecto de Felipe, `reportes-intub`).

Deliberadamente NO migra usuarios / mecanicos_talleres / ordenes_trabajo /
ot_items / eventos_mantenimiento -- esas OTs son de prueba (confirmado por
Antonio, 26-08-2026); la base nueva arranca limpia ahí, con solo el
usuario admin/supervisor inicial que crea el propio bootstrap de la app.

`item_catalogo` y las reglas de mantención con `origen='codigo'` tampoco
se copian -- se recrean solas la primera vez que la app nueva arranca
(`seed_catalogo_y_reglas`), porque viven como constantes en
`planificacion.py`. Solo se migran las reglas `origen='usuario'` (las que
Antonio ya creó a mano en Programa de Mantención), porque esas SÍ son
datos reales que no existen en el código.

Uso:
    python -m scripts.migrar_a_supabase_compartido
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from sqlalchemy import create_engine, text

from src import db, config

OLD_URL = "postgresql://postgres.lqccjphhrknitluwbtcv:q3SAM5E5BlhGC57o@aws-0-sa-east-1.pooler.supabase.com:5432/postgres"

# Tablas que se copian tal cual (datos reales, no regenerables por código).
TABLAS_DATOS_REALES = [
    "flota", "mantenimiento_registros", "faenas_registros",
    "tickets", "fallas_historico", "componentes_camion",
]


def _migrar_tabla(old_engine, new_engine, tabla: str):
    with old_engine.connect() as conn:
        df = pd.read_sql(f"SELECT * FROM mantenimiento.{tabla}", conn)
    if df.empty:
        print(f"  {tabla}: 0 filas en origen, nada que copiar")
        return
    with new_engine.connect() as conn:
        ya_tiene = conn.execute(text(f"SELECT count(*) FROM mantenimiento.{tabla}")).scalar()
    if ya_tiene:
        print(f"  {tabla}: el destino ya tiene {ya_tiene} filas -- se salta (no duplica)")
        return
    df.to_sql(tabla, new_engine, schema="mantenimiento", if_exists="append", index=False)
    print(f"  {tabla}: {len(df)} filas copiadas")


def _migrar_reglas_usuario(old_engine, new_engine):
    with old_engine.connect() as conn:
        reglas = pd.read_sql(
            "SELECT * FROM mantenimiento.reglas_mantencion WHERE origen = 'usuario'", conn,
        )
        if reglas.empty:
            print("  reglas_mantencion (origen=usuario): 0 filas, nada que copiar")
            return
        # ids son enteros que vienen de nuestra propia consulta (no de
        # input externo), así que el f-string es seguro acá.
        ids_sql = ", ".join(str(int(i)) for i in reglas["id"].tolist())
        patentes = pd.read_sql(
            f"SELECT * FROM mantenimiento.reglas_mantencion_patentes WHERE regla_id IN ({ids_sql})", conn,
        )

    with new_engine.connect() as conn:
        ya_tiene = conn.execute(text("SELECT count(*) FROM mantenimiento.reglas_mantencion WHERE origen = 'usuario'")).scalar()
    if ya_tiene:
        print(f"  reglas_mantencion (origen=usuario): el destino ya tiene {ya_tiene} -- se salta")
        return

    reglas.to_sql("reglas_mantencion", new_engine, schema="mantenimiento", if_exists="append", index=False)
    print(f"  reglas_mantencion (origen=usuario): {len(reglas)} filas copiadas")
    if not patentes.empty:
        patentes.to_sql("reglas_mantencion_patentes", new_engine, schema="mantenimiento", if_exists="append", index=False)
        print(f"  reglas_mantencion_patentes: {len(patentes)} filas copiadas")


def _resetear_secuencias(new_engine):
    """Los ids migrados se insertaron explícitos -- el contador de
    autoincremento de Postgres no se actualiza solo (mismo problema que la
    migración SQLite -> Postgres anterior). Se ajusta para cada tabla con
    secuencia."""
    with new_engine.connect() as conn:
        tablas = conn.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'mantenimiento'"
        )).scalars().all()
        for tabla in sorted(tablas):
            pk = conn.execute(text("""
                SELECT a.attname FROM pg_index i
                JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = (quote_ident('mantenimiento') || '.' || quote_ident(:tabla))::regclass
                  AND i.indisprimary
            """), {"tabla": tabla}).scalars().all()
            if len(pk) != 1:
                continue
            col = pk[0]
            seq = conn.execute(text("SELECT pg_get_serial_sequence(:full, :col)"),
                                {"full": f"mantenimiento.{tabla}", "col": col}).scalar()
            if not seq:
                continue
            maxid = conn.execute(text(f"SELECT COALESCE(MAX({col}), 0) FROM mantenimiento.{tabla}")).scalar()
            if maxid == 0:
                conn.execute(text(f"SELECT setval('{seq}', 1, false)"))
            else:
                conn.execute(text(f"SELECT setval('{seq}', :v)"), {"v": maxid})
        conn.commit()
    print("  secuencias ajustadas")


def main():
    assert config.DB_BACKEND == "postgres", "Este script es Postgres -> Postgres; revisa el .env"
    old_engine = create_engine(OLD_URL)
    new_engine = db.get_engine()

    print("1) Creando esquema y tablas en el destino (vacío, no toca nada de Felipe)...")
    db.init_db(new_engine)

    print("2) Copiando tablas de datos reales...")
    for tabla in TABLAS_DATOS_REALES:
        _migrar_tabla(old_engine, new_engine, tabla)

    print("3) Copiando reglas de mantención creadas a mano (origen=usuario)...")
    _migrar_reglas_usuario(old_engine, new_engine)

    print("4) Ajustando secuencias de autoincremento...")
    _resetear_secuencias(new_engine)

    print("Listo.")


if __name__ == "__main__":
    main()
