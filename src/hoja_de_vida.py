"""Hoja de Vida de cada camión: el historial de todo lo completado --
Inspecciones, Fallas y Mantenimiento Programado -- separado en 3
secciones, con la posibilidad de generar un Certificado de Mantenimiento
(PDF) para cada registro.

Esto lee lo que ya se completó en el Software de Mantenimiento
(`ordenes_trabajo` + `ot_items` + `ot_checklist`), no agrega una fuente de
datos nueva.
"""
import pandas as pd
from sqlalchemy import select

from src.db import ordenes_trabajo, ot_items, ot_item_sistema, tickets, eventos_mantenimiento
from src import ot_checklist


def _completados(engine, patente: str, tipo_item: str) -> pd.DataFrame:
    # El ítem cuenta apenas el mecánico lo marca "completada" (botón
    # "Finalizar tarea" en Mis OTs) -- no hace falta esperar a que se
    # cierre toda la OT, porque una OT puede traer varios ítems y el
    # mecánico los va cerrando de a uno.
    stmt = (
        select(
            ot_items.c.id.label("ot_item_id"), ot_items.c.referencia, ot_items.c.descripcion,
            ordenes_trabajo.c.numero_ot,
            ot_items.c.completado_at, ot_items.c.completado_por, ot_items.c.comentario,
            ordenes_trabajo.c.notas_cierre,
        )
        .join(ordenes_trabajo, ordenes_trabajo.c.id == ot_items.c.ot_id)
        .where(ot_items.c.patente == patente)
        .where(ot_items.c.estado == "completada")
        .where(ot_items.c.tipo_item == tipo_item)
        .order_by(ot_items.c.completado_at.desc())
    )
    with engine.connect() as conn:
        return pd.read_sql(stmt, conn)


def inspecciones_completadas(engine, patente: str) -> pd.DataFrame:
    """Una fila por checklist de Inspección completado -- `referencia` es
    el subtipo (Inicio Día / Fin Día / Semanal)."""
    return _completados(engine, patente, "inspeccion")


def fallas_completadas(engine, patente: str) -> pd.DataFrame:
    """Una fila por falla resuelta, con el sistema trabajado si se
    registró."""
    df = _completados(engine, patente, "ticket")
    if df.empty:
        df["sistema"] = pd.Series(dtype=str)
        return df
    with engine.connect() as conn:
        sistemas = pd.read_sql(select(ot_item_sistema), conn)
    df = df.merge(sistemas, left_on="ot_item_id", right_on="ot_item_id", how="left")
    return df


def mantenimientos_completados(engine, patente: str) -> pd.DataFrame:
    """Una fila por componente de Mantenimiento Programado completado."""
    return _completados(engine, patente, "item_key")


def detalle_item_completo(engine, ot_item_id: int) -> dict | None:
    """Todo lo necesario para armar el Certificado de Mantenimiento de un
    registro puntual -- cabecera de la OT + lo específico de su tipo.
    """
    stmt = (
        select(
            ot_items.c.tipo_item, ot_items.c.referencia, ot_items.c.descripcion,
            ot_items.c.patente,
            # completado_por/completado_at vienen del ítem, no de la OT --
            # una OT puede cerrarse mucho después de que este ítem
            # puntual ya estaba listo (o quedarse abierta con otros
            # ítems pendientes), así que la fecha/quién correcta es la
            # de este ítem.
            ot_items.c.completado_por, ot_items.c.completado_at, ot_items.c.comentario,
            ordenes_trabajo.c.numero_ot,
            ordenes_trabajo.c.creado_por, ordenes_trabajo.c.creado_at,
            ordenes_trabajo.c.notas_cierre,
        )
        .join(ordenes_trabajo, ordenes_trabajo.c.id == ot_items.c.ot_id)
        .where(ot_items.c.id == ot_item_id)
    )
    with engine.connect() as conn:
        base = conn.execute(stmt).mappings().first()
    if base is None:
        return None
    detalle = dict(base)
    detalle["ot_item_id"] = ot_item_id

    if detalle["tipo_item"] == "inspeccion":
        detalle["checklist"] = ot_checklist.checklist_de_ot_item(engine, ot_item_id)

    elif detalle["tipo_item"] == "ticket":
        detalle["sistema"] = ot_checklist.sistema_de_ot_item(engine, ot_item_id)
        detalle["fotos"] = ot_checklist.fotos_de_ot_item(engine, ot_item_id)
        stmt_ticket = select(
            tickets.c.code, tickets.c.description, tickets.c.name, tickets.c.priority,
        ).where(tickets.c.id == detalle["referencia"])
        with engine.connect() as conn:
            ticket_info = conn.execute(stmt_ticket).mappings().first()
        detalle["ticket"] = dict(ticket_info) if ticket_info else None

    elif detalle["tipo_item"] == "item_key":
        detalle["fotos"] = ot_checklist.fotos_de_ot_item(engine, ot_item_id)
        stmt_horas = select(eventos_mantenimiento.c.horometro).where(
            eventos_mantenimiento.c.ot_item_id == ot_item_id
        )
        with engine.connect() as conn:
            fila_horas = conn.execute(stmt_horas).fetchone()
        detalle["horometro"] = fila_horas[0] if fila_horas else None

    return detalle
