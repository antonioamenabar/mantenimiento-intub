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

flota = Table(
    "flota",
    metadata,
    Column("patente", String(20), primary_key=True),
    Column("alias", String(120)),
    Column("activo", Boolean, default=True),
)


def get_engine():
    return create_engine(config.get_database_url())


def init_db(engine=None):
    """Crea las tablas si no existen."""
    engine = engine or get_engine()
    metadata.create_all(engine)
    return engine


def upsert_registros(engine, registros: list[dict], synced_at):
    """Inserta o actualiza registros de mantenimiento (idempotente por
    form_answer_id). Funciona tanto en SQLite como en Postgres.
    """
    if not registros:
        return
    insert_fn = pg_insert if engine.dialect.name == "postgresql" else sqlite_insert
    with engine.begin() as conn:
        for r in registros:
            row = {**r, "synced_at": synced_at}
            stmt = insert_fn(mantenimiento_registros).values(**row)
            update_cols = {c.name: row[c.name] for c in mantenimiento_registros.columns
                           if c.name != "form_answer_id"}
            stmt = stmt.on_conflict_do_update(
                index_elements=["form_answer_id"], set_=update_cols
            )
            conn.execute(stmt)


def upsert_flota(engine, camiones: list[dict]):
    """Inserta o actualiza el maestro de flota (idempotente por patente)."""
    if not camiones:
        return
    insert_fn = pg_insert if engine.dialect.name == "postgresql" else sqlite_insert
    with engine.begin() as conn:
        for c in camiones:
            stmt = insert_fn(flota).values(**c)
            update_cols = {k: v for k, v in c.items() if k != "patente"}
            stmt = stmt.on_conflict_do_update(
                index_elements=["patente"], set_=update_cols
            )
            conn.execute(stmt)
