"""Capa de base de datos. Usa SQLAlchemy para poder correr en SQLite local
(desarrollo) o Postgres/Supabase (producción) sin cambiar el resto del código
— solo cambia DB_BACKEND/DATABASE_URL en el archivo .env.
"""
from sqlalchemy import (
    create_engine, MetaData, Table, Column,
    Integer, String, Boolean, DateTime, Text,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src import config

metadata = MetaData()

mantenimiento_registros = Table(
    "mantenimiento_registros",
    metadata,
    Column("form_answer_id", Integer, primary_key=True),
    Column("form_id", Integer),
    Column("patente", String(20), index=True),
    Column("tipo_mantenimiento", String(100), index=True),
    Column("fecha_inicio", String(30)),
    Column("fecha_fin", String(30)),
    Column("usuario", String(120)),
    Column("sistemas_trabajados", Text),
    Column("trabajos_realizados", Text),
    Column("fotos", Text),
    Column("finished", Boolean),
    Column("created_at", String(40)),
    Column("updated_at", String(40)),
    Column("synced_at", DateTime),
)

# "R-PR02-04 Reporte Faenas en Terreno" y "Reporte Faenas en Terreno Vitacura
# ECC" -- indican si el camión efectivamente trabajó ese día (se usa para
# saber si corresponde exigirle inspección diaria de Inicio/Fin, o si
# corresponde "N/A" porque el camión no salió a trabajar).
faenas_registros = Table(
    "faenas_registros",
    metadata,
    Column("form_answer_id", Integer, primary_key=True),
    Column("form_id", Integer),
    Column("patente", String(20), index=True),
    Column("fecha_reporte", String(30)),
    Column("created_at", String(40)),
    Column("synced_at", DateTime),
)

flota = Table(
    "flota",
    metadata,
    Column("patente", String(20), primary_key=True),
    Column("alias", String(120)),
    Column("familia", String(30)),
    Column("orden", Integer),
    Column("nombre_corto", String(60)),
    Column("activo", Boolean, default=True),
)


def get_engine():
    return create_engine(config.get_database_url())


def init_db(engine=None):
    """Crea las tablas si no existen."""
    engine = engine or get_engine()
    metadata.create_all(engine)
    return engine


def _upsert(engine, table, filas: list[dict], pk_col: str):
    """Inserta o actualiza filas de forma idempotente por `pk_col`. Funciona
    tanto en SQLite como en Postgres.
    """
    if not filas:
        return
    insert_fn = pg_insert if engine.dialect.name == "postgresql" else sqlite_insert
    with engine.begin() as conn:
        for fila in filas:
            stmt = insert_fn(table).values(**fila)
            update_cols = {k: v for k, v in fila.items() if k != pk_col}
            stmt = stmt.on_conflict_do_update(index_elements=[pk_col], set_=update_cols)
            conn.execute(stmt)


def upsert_registros(engine, registros: list[dict], synced_at):
    """Inserta o actualiza registros de mantenimiento/inspección."""
    filas = [{**r, "synced_at": synced_at} for r in registros]
    _upsert(engine, mantenimiento_registros, filas, "form_answer_id")


def upsert_faenas(engine, faenas: list[dict], synced_at):
    """Inserta o actualiza registros de Reporte de Faenas en Terreno."""
    filas = [{**f, "synced_at": synced_at} for f in faenas]
    _upsert(engine, faenas_registros, filas, "form_answer_id")


def upsert_flota(engine, camiones: list[dict]):
    """Inserta o actualiza el maestro de flota."""
    _upsert(engine, flota, camiones, "patente")
