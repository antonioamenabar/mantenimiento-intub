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

# `schema=None` en SQLite (no soporta esquemas); en Postgres, todas las
# tablas de este software quedan bajo `config.DB_SCHEMA` ("mantenimiento"),
# separadas de lo que tenga cualquier otro sistema de Intub en la misma base.
metadata = MetaData(schema=config.DB_SCHEMA)

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
#
# `datos_json` guarda el cruce prioridad x antigüedad como JSON (ej.
# {"Crítica||Menos de 7 días": 2, ..., "Total": 7}) en vez de una columna
# fija por combinación -- así, si más adelante cambian los rangos de
# antigüedad o las prioridades, no hay que migrar el esquema de la tabla.
fallas_historico = Table(
    "fallas_historico",
    metadata,
    Column("semana_inicio", String(10), primary_key=True),  # "YYYY-MM-DD" del lunes
    Column("patente", String(20), primary_key=True),
    Column("nombre_corto", String(60)),
    Column("datos_json", Text),
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

# ---------------------------------------------------------------------------
# Mantenimiento Programado (punto 2/3 del plan): catálogo de componentes
# mayores, reglas de mantención por marca/modelo, qué componente físico
# tiene instalado cada camión, y el registro de mantenciones realizadas.
# ---------------------------------------------------------------------------

# Catálogo maestro de "qué se puede registrar" -- una fila por componente
# mayor de Camión (chasis) o Equipo. Es la lista de columnas de la matriz
# del dashboard. Vive en la base (no solo en Python) para que agregar un
# ítem nuevo no requiera cambiar código, solo una fila.
item_catalogo = Table(
    "item_catalogo",
    metadata,
    Column("item_key", String(40), primary_key=True),
    Column("categoria", String(10)),  # "camion" | "equipo"
    Column("nombre", String(60)),
    Column("orden", Integer),
)

# Reglas de intervalo por componente. `marca`/`modelo` en NULL = regla
# genérica para ese item_key (la práctica de industria que usamos cuando no
# conocemos el componente exacto instalado). Si más adelante llega el manual
# oficial de una marca, se agrega una fila más específica sin tocar código.
reglas_mantencion = Table(
    "reglas_mantencion",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("item_key", String(40), index=True),
    Column("marca", String(60), nullable=True),
    Column("modelo", String(60), nullable=True),
    Column("intervalo_meses", Integer, nullable=True),
    Column("intervalo_horas", Integer, nullable=True),
    Column("confianza", String(12)),  # confirmado | estimado | sindato
    Column("fuente", Text),
)

# Qué componente físico (marca/modelo/n° de serie) tiene instalado cada
# camión -- se llena con las placas que Antonio va a mandar. Mientras no
# haya fila para un (patente, item_key), la matriz usa la regla genérica del
# item_key y lo marca como "sindato" de componente.
componentes_camion = Table(
    "componentes_camion",
    metadata,
    Column("patente", String(20), primary_key=True),
    Column("item_key", String(40), primary_key=True),
    Column("marca", String(60), nullable=True),
    Column("modelo", String(60), nullable=True),
    Column("numero_serie", String(60), nullable=True),
    Column("tiene_horometro_propio", Boolean, default=False),
)

# El registro real de mantenciones hechas. Una fila por (patente, item_key,
# fecha) -- si en una misma parada se hacen varios ítems, comparten
# `grupo_id` para poder mostrarlos agrupados como "una visita", pero cada
# ítem mantiene su propia fecha/hora de vencimiento independiente.
eventos_mantenimiento = Table(
    "eventos_mantenimiento",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("grupo_id", String(40), index=True),
    Column("patente", String(20), index=True),
    Column("item_key", String(40), index=True),
    Column("fecha", String(10)),  # "YYYY-MM-DD"
    Column("horometro", Integer, nullable=True),
    Column("tecnico", String(120), nullable=True),
    Column("detalle", Text, nullable=True),
    Column("fallas_resueltas", Text, nullable=True),
    Column("notas", Text, nullable=True),
    Column("registrado_por", String(120), nullable=True),
    Column("created_at", DateTime),
    # Qué ot_item de qué OT generó este evento -- para el Certificado de
    # Mantenimiento (Hoja de Vida). Nullable porque las bases que ya
    # tenían esta tabla antes de este campo la migran sola (ver
    # `_migrar_columnas_nuevas`).
    Column("ot_item_id", Integer, nullable=True),
)


def get_engine():
    return create_engine(config.get_database_url())


def _migrar_columnas_nuevas(engine):
    """Agrega columnas nuevas a tablas que ya existían sin ellas -- para no
    tener que borrar la base de desarrollo cada vez que se agrega un campo.
    `ALTER TABLE ... ADD COLUMN` es seguro tanto en SQLite como en Postgres
    (no toca las filas existentes, quedan con NULL en la columna nueva).
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    tablas_existentes = set(inspector.get_table_names(schema=config.DB_SCHEMA))

    # (tabla, columna, tipo SQL) -- cada vez que se agrega un campo nuevo a
    # una tabla que ya existía en bases ya desplegadas, se agrega aquí.
    COLUMNAS_NUEVAS = [
        ("eventos_mantenimiento", "ot_item_id", "INTEGER"),
        ("ordenes_trabajo", "fecha_programada", "VARCHAR(10)"),
        ("ordenes_trabajo", "turno", "VARCHAR(10)"),
        ("ot_items", "patente", "VARCHAR(20)"),
    ]

    def _nombre_completo(tabla):
        return f"{config.DB_SCHEMA}.{tabla}" if config.DB_SCHEMA else tabla

    for tabla, columna, tipo_sql in COLUMNAS_NUEVAS:
        if tabla not in tablas_existentes:
            continue  # tabla nueva, `create_all` ya la crea completa con todo
        columnas = {c["name"] for c in inspector.get_columns(tabla, schema=config.DB_SCHEMA)}
        if columna not in columnas:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {_nombre_completo(tabla)} ADD COLUMN {columna} {tipo_sql}"))

    # Backfill: OTs creadas antes de que `patente` viviera en el ítem --
    # les copiamos la patente de la cabecera a cada uno de sus ítems, una
    # sola vez (los que ya tengan patente propia quedan intactos).
    if "ordenes_trabajo" in tablas_existentes and "ot_items" in tablas_existentes:
        ot = f"{_nombre_completo('ordenes_trabajo')}"
        oi = f"{_nombre_completo('ot_items')}"
        with engine.begin() as conn:
            conn.execute(text(
                f"UPDATE {oi} SET patente = (SELECT patente FROM {ot} WHERE {ot}.id = {oi}.ot_id) "
                f"WHERE {oi}.patente IS NULL"
            ))


def init_db(engine=None):
    """Crea el esquema (solo Postgres) y las tablas si no existen, y migra
    columnas nuevas en tablas que ya existían sin ellas."""
    engine = engine or get_engine()
    if config.DB_SCHEMA:
        from sqlalchemy import text
        with engine.begin() as conn:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {config.DB_SCHEMA}"))
    metadata.create_all(engine)
    _migrar_columnas_nuevas(engine)
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


def upsert_item_catalogo(engine, items: list[dict]):
    """Inserta o actualiza el catálogo de componentes mayores (Camión/Equipo)."""
    _upsert(engine, item_catalogo, items, "item_key")


def replace_reglas_mantencion(engine, reglas: list[dict]):
    """Reemplaza por completo las reglas de mantención (borra todo y vuelve a
    insertar). Se usa reemplazo -- igual que con los tickets -- porque las
    reglas viven como constantes en `src/planificacion.py` y se reconstruyen
    completas cada vez que se corre el seed; no tiene sentido ir acumulando
    filas viejas si una regla cambió de intervalo.
    """
    with engine.begin() as conn:
        conn.execute(reglas_mantencion.delete())
        if reglas:
            conn.execute(reglas_mantencion.insert(), reglas)


def upsert_componentes_camion(engine, componentes: list[dict]):
    """Inserta o actualiza qué componente físico (marca/modelo/n° serie)
    tiene instalado cada camión. Idempotente por (patente, item_key).
    """
    _upsert(engine, componentes_camion, componentes, ["patente", "item_key"])


def insertar_eventos_mantenimiento(engine, filas: list[dict]):
    """Guarda una o más filas de mantención realizada (normalmente varias a
    la vez, una por ítem trabajado en la misma parada, compartiendo
    `grupo_id`). Siempre se inserta -- un evento real nunca se "actualiza",
    si algo quedó mal registrado se corrige registrando una corrección.
    """
    if not filas:
        return
    with engine.begin() as conn:
        conn.execute(eventos_mantenimiento.insert(), filas)


# ---------------------------------------------------------------------------
# Software de Mantenimiento: usuarios (Jefe / Mecánicos con sesión propia),
# mecánicos internos + talleres externos, y Órdenes de Trabajo (OT) con sus
# ítems. Esto es el sistema donde se CREA y ASIGNA el trabajo -- distinto
# del Dashboard (solo lectura) y de `eventos_mantenimiento` (el registro de
# lo que ya se hizo, que una OT de Mantenimiento Programado completada
# termina alimentando).
# ---------------------------------------------------------------------------

usuarios = Table(
    "usuarios",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("username", String(60), unique=True),
    Column("password_hash", String(160)),
    Column("nombre", String(120)),
    Column("rol", String(20)),  # "jefe" | "mecanico"
    Column("activo", Boolean, default=True),
    Column("created_at", DateTime),
)

# Un mecánico interno normalmente tiene `usuario_id` (puede entrar a "Mis
# OTs" a marcarlas completadas). Un taller externo no tiene usuario -- se le
# llega por email -- así que `usuario_id` queda en NULL.
mecanicos_talleres = Table(
    "mecanicos_talleres",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("tipo", String(10)),  # "interno" | "externo"
    Column("nombre", String(120)),
    Column("contacto", String(160), nullable=True),  # email y/o teléfono
    Column("usuario_id", Integer, nullable=True),
    Column("activo", Boolean, default=True),
)

ordenes_trabajo = Table(
    "ordenes_trabajo",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("numero_ot", String(20), unique=True),
    # `patente` queda solo por compatibilidad con OTs viejas (una OT ya no
    # es de un solo camión -- ver `ot_items.patente`). No se usa en OTs
    # nuevas.
    Column("patente", String(20), index=True, nullable=True),
    Column("fecha_programada", String(10), nullable=True),  # "YYYY-MM-DD", cuándo se hace el trabajo
    Column("turno", String(10), nullable=True),  # "diurno" | "nocturno"
    Column("tipo_trabajo", String(30)),  # inspeccion | fallas | mantenimiento_programado | mixta
    Column("asignado_id", Integer, index=True),  # FK mecanicos_talleres.id
    Column("estado", String(20), index=True),  # borrador | enviada | completada | cancelada
    Column("creado_por", String(60), nullable=True),
    Column("creado_at", DateTime),
    Column("enviado_at", DateTime, nullable=True),
    Column("completado_at", DateTime, nullable=True),
    Column("completado_por", String(60), nullable=True),
    Column("notas_cierre", Text, nullable=True),
)

# Las tareas concretas dentro de una OT. Una misma OT puede traer ítems de
# camiones distintos (ej. la misma Inspección Semanal para 3 camiones) --
# por eso `patente` vive en el ítem, no en la cabecera de la OT.
# `tipo_item`/`referencia` dependen del tipo de ítem:
#  - inspeccion            -> referencia = "Inicio Día" | "Fin Día" | "Semanal"
#  - fallas                -> referencia = id del ticket (tabla `tickets`)
#  - mantenimiento_programado -> referencia = item_key (tabla `item_catalogo`)
ot_items = Table(
    "ot_items",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ot_id", Integer, index=True),
    Column("patente", String(20), index=True, nullable=True),
    Column("tipo_item", String(30)),
    Column("referencia", String(60)),
    Column("descripcion", String(255), nullable=True),
)

# ---------------------------------------------------------------------------
# Lo que el mecánico completa al cerrar una OT: checklist con foto por cada
# ítem de las 3 fichas de Inspección (R-PR03-09/07/04), sistema trabajado +
# fotos antes/después en Fallas, y fotos antes/después en Mantenimiento
# Programado. Tablas nuevas (no se toca `ot_items`) para no tener que
# migrar filas ya creadas.
# ---------------------------------------------------------------------------

# Catálogo de ítems de cada ficha de Inspección -- vive en la base (no solo
# en Python) para poder ajustar una ficha sin tocar código.
inspeccion_checklist_catalogo = Table(
    "inspeccion_checklist_catalogo",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("subtipo", String(40)),  # "Inspección Inicio Día" | "Inspección Fin Día" | "Inspección Semanal"
    Column("grupo", String(40)),  # "Camión" | "Equipo" | "Cabina" | "Herramientas" | ...
    Column("item", String(160)),
    Column("orden", Integer),
)

# La respuesta del mecánico a UN ítem del catálogo, al completar un
# ot_item de tipo "inspeccion". `foto_ruta` es la ruta relativa del
# archivo guardado en disco (ver `src/ot_checklist.py`).
inspeccion_checklist_respuestas = Table(
    "inspeccion_checklist_respuestas",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ot_item_id", Integer, index=True),
    Column("catalogo_id", Integer, index=True),
    Column("estado", String(20)),  # "normal" | "fuera_normal"
    Column("observacion", Text, nullable=True),
    Column("foto_ruta", String(255), nullable=True),
)

# Qué sistema se trabajó en un ot_item de Fallas (tipo_item="ticket") --
# una fila por ot_item, de la lista fija de 11 sistemas.
ot_item_sistema = Table(
    "ot_item_sistema",
    metadata,
    Column("ot_item_id", Integer, primary_key=True),
    Column("sistema", String(120)),
)

# Fotos "antes"/"después" -- se usan en Fallas y en Mantenimiento
# Programado (en Inspección la foto va colgada de cada respuesta del
# checklist, no acá).
ot_item_fotos = Table(
    "ot_item_fotos",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ot_item_id", Integer, index=True),
    Column("momento", String(10)),  # "antes" | "despues"
    Column("ruta", String(255)),
)


def upsert_mecanico_taller(engine, fila: dict) -> int:
    """Crea o actualiza un mecánico interno / taller externo. Si `fila`
    trae "id", actualiza esa fila; si no, inserta una nueva. Devuelve el id.
    """
    with engine.begin() as conn:
        if fila.get("id"):
            conn.execute(
                mecanicos_talleres.update()
                .where(mecanicos_talleres.c.id == fila["id"])
                .values(**{k: v for k, v in fila.items() if k != "id"})
            )
            return fila["id"]
        # Se omite la clave "id" (aunque venga como None) -- en Postgres,
        # insertar NULL explícito en una columna autoincremental NO la deja
        # generar el valor por defecto (a diferencia de SQLite, donde
        # insertar NULL en el INTEGER PRIMARY KEY sí autogenera el rowid).
        result = conn.execute(mecanicos_talleres.insert().values(**{k: v for k, v in fila.items() if k != "id"}))
        return result.inserted_primary_key[0]


def crear_usuario(engine, username: str, password_hash: str, nombre: str, rol: str, created_at) -> int:
    with engine.begin() as conn:
        result = conn.execute(usuarios.insert().values(
            username=username, password_hash=password_hash, nombre=nombre,
            rol=rol, activo=True, created_at=created_at,
        ))
        return result.inserted_primary_key[0]


def actualizar_password(engine, usuario_id: int, password_hash: str):
    with engine.begin() as conn:
        conn.execute(
            usuarios.update().where(usuarios.c.id == usuario_id).values(password_hash=password_hash)
        )


def crear_orden_trabajo(engine, ot: dict, items: list[dict]) -> int:
    """Crea la OT (cabecera) y sus ítems en una sola transacción. Devuelve
    el id de la OT creada.
    """
    with engine.begin() as conn:
        result = conn.execute(ordenes_trabajo.insert().values(**ot))
        ot_id = result.inserted_primary_key[0]
        if items:
            conn.execute(ot_items.insert(), [{**it, "ot_id": ot_id} for it in items])
        return ot_id


def actualizar_estado_ot(engine, ot_id: int, **campos):
    with engine.begin() as conn:
        conn.execute(ordenes_trabajo.update().where(ordenes_trabajo.c.id == ot_id).values(**campos))


def replace_checklist_catalogo(engine, filas: list[dict]):
    """Reemplaza por completo el catálogo de checklist (igual criterio que
    `replace_reglas_mantencion`: vive como constante en Python, se
    reconstruye entero cada vez que corre el seed).
    """
    with engine.begin() as conn:
        conn.execute(inspeccion_checklist_catalogo.delete())
        if filas:
            conn.execute(inspeccion_checklist_catalogo.insert(), filas)


def guardar_respuestas_checklist(engine, filas: list[dict]):
    if not filas:
        return
    with engine.begin() as conn:
        conn.execute(inspeccion_checklist_respuestas.insert(), filas)


def guardar_sistema_ot_item(engine, ot_item_id: int, sistema: str):
    """Upsert -- mismo patrón que `_upsert`, elige el dialecto según el
    backend (sqlite en desarrollo, postgres en producción)."""
    insert_fn = pg_insert if engine.dialect.name == "postgresql" else sqlite_insert
    with engine.begin() as conn:
        stmt = insert_fn(ot_item_sistema).values(ot_item_id=ot_item_id, sistema=sistema)
        stmt = stmt.on_conflict_do_update(index_elements=["ot_item_id"], set_={"sistema": sistema})
        conn.execute(stmt)


def guardar_foto_ot_item(engine, ot_item_id: int, momento: str, ruta: str):
    with engine.begin() as conn:
        conn.execute(ot_item_fotos.insert().values(ot_item_id=ot_item_id, momento=momento, ruta=ruta))
