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

# Tickets de fallas (menú "Tickets" en Datascope, endpoint /findings/list).
tickets = Table(
    "tickets",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("code", Integer),
    Column("name", String(255)),
    Column("description", Text),
    Column("status", String(30), index=True),
    Column("priority", String(20), index=True),
    Column("patente", String(20), index=True),
    Column("asset_identifier", String(20)),
    Column("creation_date", String(40)),
    Column("expiration_date", String(40)),
    Column("closure_date", String(40)),
    Column("closure_message", Text),
    Column("creator_name", String(120)),
    Column("synced_at", DateTime),
)

# Foto histórica semanal del cuadrante de Fallas -- se llena con
# src/snapshot_fallas.py, pensado para correr cada lunes 8:00 AM vía Tarea
# Programada de Windows. Clave compuesta (semana_inicio, patente).
fallas_historico = Table(
    "fallas_historico",
    metadata,
    Column("semana_inicio", String(10), primary_key=True),  # "YYYY-MM-DD" del lunes
    Column("patente", String(20), primary_key=True),
    Column("nombre_corto", String(60)),
    Column("critica", Integer),
    Column("alta", Integer),
    Column("media", Integer),
    Column("baja", Integer),
    Column("menos_7_dias", Integer),
    Column("entre_8_20_dias", Integer),
    Column("mas_20_dias", Integer),
    Column("total", Integer),
    Column("snapshot_at", DateTime),
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


def _upsert(engine, table, filas: list[dict], pk_cols: str | list[str]):
    """Inserta o actualiza filas de forma idempotente por `pk_cols` (una
    columna o una lista, para clave compuesta). Funciona tanto en SQLite
    como en Postgres.
    """
    if not filas:
        return
    if isinstance(pk_cols, str):
        pk_cols = [pk_cols]
    insert_fn = pg_insert if engine.dialect.name == "postgresql" else sqlite_insert
    with engine.begin() as conn:
        for fila in filas:
            stmt = insert_fn(table).values(**fila)
            update_cols = {k: v for k, v in fila.items() if k not in pk_cols}
            stmt = stmt.on_conflict_do_update(index_elements=pk_cols, set_=update_cols)
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


def replace_tickets(engine, filas_tickets: list[dict], synced_at):
    """Reemplaza por completo la tabla de tickets (borra todo y vuelve a
    insertar). Se usa reemplazo en vez de upsert porque solo se sincronizan
    los tickets NO cerrados -- si se hiciera upsert, un ticket que se cierra
    en Datascope nunca se volvería a traer (ya no matchea el filtro) y
    quedaría "pegado" en la base local mostrando un estado open desactualizado.
    """
    filas = [{**t, "synced_at": synced_at} for t in filas_tickets]
    with engine.begin() as conn:
        conn.execute(tickets.delete())
        if filas:
            conn.execute(tickets.insert(), filas)


def upsert_fallas_historico(engine, filas_historico: list[dict], snapshot_at):
    """Guarda (o actualiza si ya existía) la foto histórica de Fallas de una
    semana. Idempotente por (semana_inicio, patente) -- correr el snapshot
    dos veces para la misma semana simplemente actualiza los mismos datos.
    """
    filas = [{**f, "snapshot_at": snapshot_at} for f in filas_historico]
    _upsert(engine, fallas_historico, filas, ["semana_inicio", "patente"])
