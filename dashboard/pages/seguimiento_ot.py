"""Seguimiento OT - Intub

Vista de todas las Órdenes de Trabajo y su estado -- para cerrar/cancelar
una OT puntual, ver "Mis OTs".
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

from src import auth, hoja_de_vida as hv, ordenes_trabajo as ot, ot_checklist as chk
from src.bootstrap import get_engine
from src.flash import mostrar_flash

engine = get_engine()
usuario = auth.requerir_login(rol_requerido=auth.ROLES_OPERACION)

st.markdown("<h1 style='text-align:center;'>📋 Seguimiento OT</h1>", unsafe_allow_html=True)
mostrar_flash()

_ETIQUETA_TIPO_ITEM = {"inspeccion": "Inspección", "ticket": "Falla", "item_key": "Mantenimiento Programado"}
_ESTADO_ITEM_LABEL = {"pendiente": "Pendiente", "completada": "Completada"}


def _fecha(valor) -> str:
    return valor.strftime("%d-%m-%Y %H:%M") if pd.notna(valor) else "—"


def _texto(valor):
    return valor if pd.notna(valor) and str(valor).strip() else None


def _detalle_item_completado(ot_item_id: int):
    """Lo que se guardó al marcar "Finalizar tarea" en Mis OTs -- checklist
    de Inspección, sistema/fotos de una Falla, u horómetro/fotos de un
    Mantenimiento Programado. Reutiliza `hoja_de_vida.detalle_item_completo`
    (misma función que arma el Certificado de Mantención) para no duplicar
    esta lógica.
    """
    detalle = hv.detalle_item_completo(engine, ot_item_id)
    if detalle is None:
        return

    if detalle["tipo_item"] == "inspeccion":
        checklist = detalle["checklist"]
        if checklist.empty:
            st.caption("Sin checklist guardado.")
        else:
            vista = checklist.rename(columns={
                "grupo": "Grupo", "item": "Ítem", "estado": "Estado", "observacion": "Observación", "valor": "Valor",
            })
            vista["Fotos"] = checklist["fotos"].apply(len)
            st.dataframe(
                vista[["Grupo", "Ítem", "Estado", "Observación", "Valor", "Fotos"]],
                hide_index=True, width="stretch",
            )

    elif detalle["tipo_item"] == "ticket":
        if detalle.get("sistema"):
            st.caption(f"Sistema trabajado: {detalle['sistema']}")
        st.caption(f"Fotos adjuntas: {len(detalle['fotos'])}")

    elif detalle["tipo_item"] == "item_key":
        if detalle.get("horometro") is not None:
            st.caption(f"Horómetro registrado: {detalle['horometro']}")
        st.caption(f"Fotos adjuntas: {len(detalle['fotos'])}")

    comentario = _texto(detalle.get("comentario"))
    if comentario:
        st.caption(f"Comentario del mecánico: {comentario}")


@st.dialog("Detalle de la OT")
def _dialog_detalle_ot(fila_ot: dict):
    st.markdown(f"**{fila_ot['numero_ot']}** — {ot.ESTADO_LABEL.get(fila_ot['estado'], fila_ot['estado'])}")
    st.caption(
        f"Programada: {fila_ot['fecha_programada'] or '—'} "
        f"({ot.TURNO_LABEL.get(fila_ot['turno'], '—')}) · "
        f"Camiones: {fila_ot['patentes']} · Asignada a: {fila_ot['asignados_nombres']}"
    )
    st.caption(f"Creada por {fila_ot['creado_por'] or '—'} el {_fecha(fila_ot['creado_at'])}")
    if fila_ot["estado"] == "completada":
        st.caption(f"Completada por {fila_ot['completado_por'] or '—'} el {_fecha(fila_ot['completado_at'])}")
    notas_cierre = _texto(fila_ot.get("notas_cierre"))
    if notas_cierre:
        st.caption(f"Notas de cierre: {notas_cierre}")
    notas_pendientes = _texto(fila_ot.get("notas_pendientes"))
    if notas_pendientes:
        st.caption(f"Notas de ítems pendientes: {notas_pendientes}")
    motivo_cancelacion = _texto(fila_ot.get("motivo_cancelacion"))
    if motivo_cancelacion:
        st.caption(f"Motivo de cancelación: {motivo_cancelacion}")

    st.divider()

    items = ot.items_de_ot(engine, int(fila_ot["id"]))
    if items.empty:
        st.info("Esta OT no tiene ítems.")
    else:
        for _, item in items.iterrows():
            titulo = (
                f"{_ESTADO_ITEM_LABEL.get(item['estado'], item['estado'])} — "
                f"{_ETIQUETA_TIPO_ITEM.get(item['tipo_item'], item['tipo_item'])} — "
                f"{item['descripcion'] or item['referencia']} ({item['patente'] or '—'})"
            )
            with st.expander(titulo):
                if item["estado"] == "completada":
                    _detalle_item_completado(int(item["id"]))
                else:
                    st.caption("Todavía no se ha completado.")

    if st.button("Cerrar", key="cerrar_detalle_ot"):
        st.session_state["seguimiento_ot_sel"] = {"selection": {"rows": [], "columns": [], "cells": []}}
        st.rerun()


estados = ["Todas"] + list(ot.ESTADO_LABEL.values())
estado_sel = st.selectbox("Estado", options=estados, key="seguimiento_estado")
estado_key = None
if estado_sel != "Todas":
    estado_key = {v: k for k, v in ot.ESTADO_LABEL.items()}[estado_sel]

tabla = ot.ots_todas(engine, estado=estado_key).reset_index(drop=True)
if tabla.empty:
    st.info("No hay OTs para mostrar.")
else:
    tabla_mostrar = tabla.copy()
    tabla_mostrar["tipo_trabajo"] = tabla_mostrar["tipo_trabajo"].map(ot.TIPO_TRABAJO_LABEL)
    tabla_mostrar["estado"] = tabla_mostrar["estado"].map(ot.ESTADO_LABEL)
    tabla_mostrar["turno"] = tabla_mostrar["turno"].map(ot.TURNO_LABEL).fillna("—")
    tabla_mostrar["fecha_programada"] = tabla_mostrar["fecha_programada"].fillna("—")

    st.caption("Selecciona una fila (clic en cualquier celda) para ver el detalle completo de esa OT.")
    evento = st.dataframe(
        tabla_mostrar[[
            "numero_ot", "fecha_programada", "turno", "patentes", "tipo_trabajo",
            "asignados_nombres", "estado", "creado_at", "completado_at",
        ]].rename(columns={
            "numero_ot": "OT", "fecha_programada": "Fecha", "turno": "Turno",
            "patentes": "Camiones", "tipo_trabajo": "Tipo",
            "asignados_nombres": "Asignado a",
            "estado": "Estado", "creado_at": "Creada", "completado_at": "Completada",
        }),
        hide_index=True, width="content",
        on_select="rerun", selection_mode="single-row",
        key="seguimiento_ot_sel",
    )

    filas_sel = evento["selection"]["rows"] if evento else []
    if filas_sel:
        _dialog_detalle_ot(tabla.iloc[filas_sel[0]].to_dict())
