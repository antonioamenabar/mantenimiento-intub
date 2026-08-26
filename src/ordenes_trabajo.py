"""Software de Mantenimiento: creación, envío y cierre de Órdenes de
Trabajo (OT). Este módulo es el que sabe *asignar y despachar* trabajo --
distinto de `planificacion.py`, que sabe *cuándo corresponde* mantención, y
de `queries.py`, que sabe qué pasó en Inspecciones/Fallas según Datascope.

Flujo: el Jefe arma un borrador de OT en memoria (sesión de Streamlit) →
lo revisa → al aprobar, se escribe una sola vez en `ordenes_trabajo` +
`ot_items` con estado "enviada", y se despacha (aparece en "Mis OTs" del
mecánico interno, o se manda un email al taller externo) → cuando se
completa, si la OT era de Mantenimiento Programado, cada ítem se traduce
en un evento real de `eventos_mantenimiento` (así el Dashboard se entera).
"""
import os
import smtplib
from datetime import datetime
from email.mime.text import MIMEText

import pandas as pd
from sqlalchemy import select, func, or_

from src.db import (
    mecanicos_talleres, ordenes_trabajo, ot_items, ot_asignados, tickets,
    upsert_mecanico_taller, crear_orden_trabajo, actualizar_estado_ot,
)
from src.queries import PRIORIDADES, PRIORIDAD_LABEL, _dias_antiguedad
from src import planificacion

TIPOS_TRABAJO = [
    ("inspeccion", "Inspección"),
    ("fallas", "Fallas"),
    ("mantenimiento_programado", "Mantenimiento Programado"),
]
TIPO_TRABAJO_LABEL = dict(TIPOS_TRABAJO) | {"mixta": "Mixta"}

SUBTIPOS_INSPECCION = ["Inspección Inicio Día", "Inspección Fin Día", "Inspección Semanal"]

# Une el tipo_item de un ítem de OT con la categoría de trabajo a la que
# pertenece -- una OT puede mezclar las 3 (ver `tipo_trabajo_resumen`).
_TIPO_ITEM_A_CATEGORIA = {
    "inspeccion": "inspeccion", "ticket": "fallas", "item_key": "mantenimiento_programado",
}


def tipo_trabajo_resumen(items: list[dict]) -> str:
    """Etiqueta de resumen para el header de la OT: si todos los ítems son
    de la misma categoría, esa; si mezcla más de una, "mixta". Una OT ya no
    está limitada a un solo tipo de trabajo -- puede traer Inspección,
    Fallas y Mantenimiento Programado juntos.
    """
    categorias = {_TIPO_ITEM_A_CATEGORIA.get(it["tipo_item"], "otro") for it in items}
    return categorias.pop() if len(categorias) == 1 else "mixta"


ESTADO_LABEL = {
    "borrador": "Borrador", "enviada": "Enviada",
    "completada": "Completada", "cancelada": "Cancelada",
}


# ---------------------------------------------------------------------------
# Mecánicos internos / talleres externos
# ---------------------------------------------------------------------------

def mecanicos_talleres_activos(engine, tipo: str | None = None) -> pd.DataFrame:
    stmt = select(mecanicos_talleres).where(mecanicos_talleres.c.activo.is_(True))
    if tipo:
        stmt = stmt.where(mecanicos_talleres.c.tipo == tipo)
    with engine.connect() as conn:
        df = pd.read_sql(stmt, conn)
    if df.empty:
        return pd.DataFrame(columns=["id", "tipo", "nombre", "contacto", "usuario_id", "activo"])
    return df


def guardar_mecanico_taller(engine, id, tipo, nombre, contacto, usuario_id=None) -> int:
    return upsert_mecanico_taller(engine, {
        "id": id, "tipo": tipo, "nombre": nombre, "contacto": contacto or None,
        "usuario_id": usuario_id, "activo": True,
    })


def desactivar_mecanico_taller(engine, id):
    upsert_mecanico_taller(engine, {"id": id, "activo": False})


# ---------------------------------------------------------------------------
# Listas para armar el borrador de la OT (paso 2 y 3 del asistente)
# ---------------------------------------------------------------------------

DATASCOPE_TICKETS_URL = "https://app.mydatascope.com/issues"


def _referencias_asignadas(engine, tipo_item: str, patente: str) -> dict:
    """`referencia` -> `numero_ot`, para ítems de tipo `tipo_item` de este
    camión que ya están en una OT "enviada" (todavía no completada). Sirve
    para no dejar asignar dos veces lo mismo a dos mecánicos distintos --
    una vez que la OT que lo tiene se completa (o se cancela), deja de
    contar como asignado.
    """
    stmt = (
        select(ot_items.c.referencia, ordenes_trabajo.c.numero_ot)
        .join(ordenes_trabajo, ordenes_trabajo.c.id == ot_items.c.ot_id)
        .where(ot_items.c.tipo_item == tipo_item)
        .where(ot_items.c.patente == patente)
        .where(ordenes_trabajo.c.estado == "enviada")
        # Si el mecánico ya cerró este ítem puntual (aunque el resto de la
        # OT siga abierto), ya no cuenta como "asignado" -- el trabajo real
        # ya se hizo. `or_` con `is_(None)` porque en SQL "NULL != valor"
        # da NULL (no verdadero) y dejaría afuera del filtro, sin querer,
        # a cualquier ítem viejo que no tenga `estado` seteado.
        .where(or_(ot_items.c.estado.is_(None), ot_items.c.estado != "completada"))
    )
    with engine.connect() as conn:
        filas = conn.execute(stmt).fetchall()
    return {r[0]: r[1] for r in filas}


def fallas_asignadas(engine, patente: str) -> dict:
    """ticket_id (str) -> numero_ot, para fallas de este camión ya
    asignadas a una OT en curso."""
    return _referencias_asignadas(engine, "ticket", patente)


def items_mantenimiento_asignados(engine, patente: str) -> dict:
    """item_key -> numero_ot, para ítems de Mantenimiento Programado de
    este camión ya asignados a una OT en curso."""
    return _referencias_asignadas(engine, "item_key", patente)


def fallas_para_ot(engine, patente: str) -> pd.DataFrame:
    """Fallas abiertas de un camión, ordenadas de más crítica+antigua a
    menos -- el orden que pidió Antonio para elegir qué entra en la OT.
    `descripcion` es el campo real de contenido (`description` en
    Datascope) -- `name` en los tickets de Intub suele traer solo la
    patente, no una descripción del problema.
    """
    stmt = (
        select(
            tickets.c.id, tickets.c.code, tickets.c.name, tickets.c.description,
            tickets.c.priority, tickets.c.creation_date, tickets.c.creator_name,
        )
        .where(tickets.c.patente == patente)
    )
    with engine.connect() as conn:
        df = pd.read_sql(stmt, conn)
    columnas = [
        "id", "code", "name", "description", "descripcion", "priority",
        "creation_date", "creator_name", "dias",
    ]
    if df.empty:
        return pd.DataFrame(columns=columnas)
    orden_prioridad = {p: i for i, p in enumerate(PRIORIDADES)}
    df["_orden_prioridad"] = df["priority"].map(orden_prioridad).fillna(len(PRIORIDADES))
    df["dias"] = df["creation_date"].apply(_dias_antiguedad)
    df["descripcion"] = df.apply(
        lambda r: (r["description"] or r["name"] or "").strip() or "(sin descripción)", axis=1,
    )
    df = df.sort_values(["_orden_prioridad", "dias"], ascending=[True, False])
    return df.drop(columns="_orden_prioridad").reset_index(drop=True)


def falla_por_id(engine, ticket_id: str) -> dict | None:
    """Un ticket puntual, para el popup de detalle al hacer clic en su N°.
    Datascope no expone fotos ni comentarios por la API externa (se probó
    /findings/get con `expand`/`include` de comentarios y no trae nada
    nuevo, y su web no cambia de URL al abrir un ticket, así que tampoco
    se puede armar un link directo) -- por eso el popup muestra todo el
    detalle disponible y un botón genérico a Datascope para buscarlo ahí
    si hace falta ver la foto adjunta.
    """
    stmt = select(
        tickets.c.code, tickets.c.name, tickets.c.description, tickets.c.priority,
        tickets.c.creation_date, tickets.c.creator_name, tickets.c.status,
    ).where(tickets.c.id == ticket_id)
    with engine.connect() as conn:
        fila = conn.execute(stmt).mappings().first()
    return dict(fila) if fila else None


def items_mantenimiento_para_ot(engine, patente: str) -> pd.DataFrame:
    """Catálogo de componentes de un camión con su estado de vencimiento
    actual, para que el Jefe vea qué está atrasado al armar la OT.
    `horas_venc` son horas de calendario hasta el vencimiento (negativas si
    ya venció); `None` cuando el ítem nunca se ha registrado -- ahí no hay
    fecha base desde la cual contar.
    """
    items_df = planificacion.catalogo_items(engine)
    matriz = planificacion.matriz_mantenimiento(engine, patentes=[patente])
    if matriz.empty:
        items_df["estado"] = "sin_evento"
        items_df["horas_venc"] = None
        return items_df
    fila = matriz.iloc[0]
    items_df["estado"] = items_df["item_key"].apply(lambda k: fila[k]["estado"])
    items_df["horas_venc"] = items_df["item_key"].apply(lambda k: fila[k]["horas_restantes"])
    return items_df


# ---------------------------------------------------------------------------
# Crear / enviar la OT
# ---------------------------------------------------------------------------

def _siguiente_numero_ot(engine) -> str:
    with engine.connect() as conn:
        maximo = conn.execute(select(func.max(ordenes_trabajo.c.id))).scalar()
    return f"OT-{(maximo or 0) + 1:04d}"


def crear_y_enviar_ot(
    engine, fecha_programada, turno: str, asignados_ids: list[int], items: list[dict], creado_por: str,
) -> dict:
    """Crea la OT con sus ítems y la despacha. Puede ir a más de un
    mecánico/taller a la vez (trabajan en parejas):
      - a cada asignado interno -> le queda visible de inmediato en
        "Mis OTs" (no hace falta hacer nada más, es la misma tabla).
      - a cada asignado externo con contacto -> se le manda un email con
        el detalle (uno por taller, si se asignó más de uno).
    Una sola OT puede traer ítems de Inspección, Fallas y Mantenimiento
    Programado a la vez, de camiones distintos -- cada ítem trae su propia
    `patente` (ver `tipo_trabajo_resumen` para el resumen de tipo).
    Devuelve {"ot_id", "numero_ot", "emails_enviados", "emails_error"}.
    """
    ahora = datetime.now()
    numero_ot = _siguiente_numero_ot(engine)
    tipo_trabajo = tipo_trabajo_resumen(items)
    fecha_str = fecha_programada.strftime("%Y-%m-%d") if hasattr(fecha_programada, "strftime") else str(fecha_programada)
    ot_id = crear_orden_trabajo(engine, {
        "numero_ot": numero_ot, "patente": None, "fecha_programada": fecha_str, "turno": turno,
        "tipo_trabajo": tipo_trabajo, "asignado_id": None, "estado": "enviada",
        "creado_por": creado_por, "creado_at": ahora, "enviado_at": ahora,
    }, items, asignados_ids=asignados_ids)

    asignables = mecanicos_talleres_activos(engine)
    asignados = asignables[asignables["id"].isin(asignados_ids)].to_dict("records")

    emails_enviados, emails_error = [], []
    for asignado in asignados:
        if asignado["tipo"] == "externo" and asignado.get("contacto"):
            try:
                _enviar_email_ot(numero_ot, fecha_str, turno, tipo_trabajo, items, asignado["contacto"])
                emails_enviados.append(asignado["nombre"])
            except Exception as exc:  # noqa: BLE001 -- se muestra el motivo al Jefe, no se rompe la OT
                emails_error.append(f"{asignado['nombre']}: {exc}")

    return {
        "ot_id": ot_id, "numero_ot": numero_ot,
        "emails_enviados": emails_enviados, "emails_error": emails_error,
    }


TURNO_LABEL = {"diurno": "Diurno", "nocturno": "Nocturno"}


def _enviar_email_ot(numero_ot: str, fecha_str: str, turno: str, tipo_trabajo: str, items: list[dict], destinatario: str):
    """Envía la OT por correo a un taller externo, usando las credenciales
    SMTP del archivo .env (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
    SMTP_FROM). Si no están configuradas, lanza un error claro en vez de
    fallar silenciosamente -- así el Jefe sabe que tiene que configurarlas.
    """
    host = os.getenv("SMTP_HOST")
    puerto = int(os.getenv("SMTP_PORT", "587"))
    usuario = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    remitente = os.getenv("SMTP_FROM", usuario or "")

    if not host or not usuario or not password:
        raise RuntimeError(
            "Faltan credenciales de correo en el archivo .env "
            "(SMTP_HOST, SMTP_USER, SMTP_PASSWORD) -- la OT quedó creada pero no se pudo enviar el email."
        )

    patentes = sorted({it.get("patente") for it in items if it.get("patente")})
    detalle = "\n".join(f"- ({it.get('patente', '—')}) {it.get('descripcion') or it.get('referencia')}" for it in items)
    cuerpo = (
        f"Orden de Trabajo {numero_ot}\n"
        f"Fecha: {fecha_str} -- Turno: {TURNO_LABEL.get(turno, turno)}\n"
        f"Camiones: {', '.join(patentes) or '—'}\n"
        f"Tipo de trabajo: {TIPO_TRABAJO_LABEL.get(tipo_trabajo, tipo_trabajo)}\n\n"
        f"Ítems:\n{detalle}\n\n"
        f"-- Enviado automáticamente por el Software de Mantenimiento de Intub."
    )
    mensaje = MIMEText(cuerpo, "plain", "utf-8")
    mensaje["Subject"] = f"{numero_ot} - {', '.join(patentes) or 'varios'} - {TIPO_TRABAJO_LABEL.get(tipo_trabajo, tipo_trabajo)}"
    mensaje["From"] = remitente
    mensaje["To"] = destinatario

    with smtplib.SMTP(host, puerto, timeout=20) as servidor:
        servidor.starttls()
        servidor.login(usuario, password)
        servidor.sendmail(remitente, [destinatario], mensaje.as_string())


# ---------------------------------------------------------------------------
# Consultar / completar OTs
# ---------------------------------------------------------------------------

def _cargar_ots(engine, where=None) -> pd.DataFrame:
    stmt = select(ordenes_trabajo).order_by(ordenes_trabajo.c.creado_at.desc())
    if where is not None:
        stmt = stmt.where(where)
    with engine.connect() as conn:
        df = pd.read_sql(stmt, conn)
    if df.empty:
        df["patentes"] = pd.Series(dtype=str)
        df["asignados_nombres"] = pd.Series(dtype=str)
        return df

    with engine.connect() as conn:
        items_df = pd.read_sql(
            select(ot_items.c.ot_id, ot_items.c.patente).where(ot_items.c.ot_id.in_(df["id"].tolist())), conn,
        )
        asignados_df = pd.read_sql(
            select(ot_asignados.c.ot_id, mecanicos_talleres.c.nombre)
            .join(mecanicos_talleres, mecanicos_talleres.c.id == ot_asignados.c.mecanico_id)
            .where(ot_asignados.c.ot_id.in_(df["id"].tolist())),
            conn,
        )
    # Camiones distintos que trae la OT, para mostrar en el listado -- una
    # OT ya no es de un solo camión, así que la columna "patente" de la
    # cabecera no basta.
    patentes_por_ot = (
        items_df.dropna(subset=["patente"]).groupby("ot_id")["patente"]
        .apply(lambda s: ", ".join(sorted(set(s))))
    )
    df["patentes"] = df["id"].map(patentes_por_ot).fillna("—")
    # Puede ir a más de un mecánico/taller a la vez (trabajan en parejas).
    asignados_por_ot = asignados_df.groupby("ot_id")["nombre"].apply(lambda s: ", ".join(s))
    df["asignados_nombres"] = df["id"].map(asignados_por_ot).fillna("—")
    return df


def ots_de_usuario(engine, usuario_id: int) -> pd.DataFrame:
    """OTs asignadas a un mecánico interno (su propia sesión) -- incluye
    las que comparte con otro mecánico (van en pareja)."""
    ot_ids_del_usuario = (
        select(ot_asignados.c.ot_id)
        .join(mecanicos_talleres, mecanicos_talleres.c.id == ot_asignados.c.mecanico_id)
        .where(mecanicos_talleres.c.usuario_id == usuario_id)
    )
    return _cargar_ots(engine, where=ordenes_trabajo.c.id.in_(ot_ids_del_usuario))


def ots_todas(engine, estado: str | None = None) -> pd.DataFrame:
    """Vista de seguimiento del Jefe -- todas las OTs, opcionalmente
    filtradas por estado.
    """
    where = (ordenes_trabajo.c.estado == estado) if estado else None
    return _cargar_ots(engine, where=where)


def items_de_ot(engine, ot_id: int) -> pd.DataFrame:
    stmt = select(ot_items).where(ot_items.c.ot_id == ot_id)
    with engine.connect() as conn:
        return pd.read_sql(stmt, conn)


def item_por_id(engine, ot_item_id: int) -> dict | None:
    stmt = select(ot_items).where(ot_items.c.id == ot_item_id)
    with engine.connect() as conn:
        fila = conn.execute(stmt).mappings().first()
    return dict(fila) if fila else None


def completar_item(
    engine, ot_item_id: int, completado_por: str,
    horometro: int | None = None, comentario: str = "",
):
    """Cierra UN ítem puntual de la OT, independiente del resto -- el
    mecánico va marcando cada Inspección/Falla/Mantenimiento como
    "Finalizar tarea" a medida que las termina, sin esperar a cerrar toda
    la OT. `comentario` es libre y opcional, para cualquier tipo de tarea.
    Si es un ítem de Mantenimiento Programado, registra el evento real ahí
    mismo (no se espera al cierre de la OT completa), así el Dashboard se
    entera apenas se hace el trabajo.
    """
    ahora = datetime.now()
    fila_item = item_por_id(engine, ot_item_id)
    with engine.begin() as conn:
        conn.execute(
            ot_items.update().where(ot_items.c.id == ot_item_id)
            .values(
                estado="completada", completado_at=ahora, completado_por=completado_por,
                comentario=comentario or None,
            )
        )
    if fila_item and fila_item["tipo_item"] == "item_key":
        planificacion.registrar_evento(
            engine, patente=fila_item["patente"], items=[fila_item["referencia"]], fecha=ahora.date(),
            horometro=horometro, tecnico=completado_por,
            detalle=comentario, registrado_por=completado_por, ot_item_id=ot_item_id,
        )


def completar_ot(engine, ot_id: int, completado_por: str, notas_cierre: str = "", notas_pendientes: str = ""):
    """Cierra la OT completa. Los ítems que el mecánico ya fue marcando con
    `completar_item` quedan tal cual (con su propia fecha y quién los
    hizo); si queda alguno todavía "pendiente", `notas_pendientes` es
    obligatorio (se valida en la UI, y de nuevo acá por si se llama
    directo) -- así queda registrado por qué no se alcanzó a terminar.
    """
    items = items_de_ot(engine, ot_id)
    pendientes = items[items["estado"] != "completada"]
    if not pendientes.empty and not (notas_pendientes or "").strip():
        raise ValueError(
            "Quedan tareas pendientes en esta OT -- hay que explicar por qué antes de cerrarla."
        )
    ahora = datetime.now()
    actualizar_estado_ot(
        engine, ot_id, estado="completada", completado_at=ahora,
        completado_por=completado_por, notas_cierre=notas_cierre or None,
        notas_pendientes=notas_pendientes or None,
    )


def cancelar_ot(engine, ot_id: int, motivo: str = ""):
    """Cancela la OT completa (la usa el Supervisor/Admin desde "Mis OTs").
    Los ítems que el mecánico ya había finalizado con `completar_item` NO
    se tocan -- ese trabajo ya quedó hecho y registrado (fotos, eventos de
    mantenimiento, Hoja de Vida). Los que seguían "pendiente" se marcan
    "cancelada" y quedan libres para poder asociarse a una OT nueva --
    `_referencias_asignadas` solo bloquea por ítems de una OT "enviada",
    así que apenas esta OT deja de estarlo, Fallas y Mantenimiento
    Programado vuelven a aparecer disponibles.
    """
    with engine.begin() as conn:
        conn.execute(
            ordenes_trabajo.update().where(ordenes_trabajo.c.id == ot_id)
            .values(estado="cancelada", motivo_cancelacion=motivo or None)
        )
        conn.execute(
            ot_items.update()
            .where(ot_items.c.ot_id == ot_id)
            .where(or_(ot_items.c.estado.is_(None), ot_items.c.estado != "completada"))
            .values(estado="cancelada")
        )
