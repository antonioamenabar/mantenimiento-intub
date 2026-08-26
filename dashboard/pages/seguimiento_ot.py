"""Seguimiento OT - Intub

Vista de todas las Órdenes de Trabajo y su estado -- para cerrar/cancelar
una OT puntual, ver "Mis OTs".
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from src import auth, ordenes_trabajo as ot
from src.bootstrap import get_engine
from src.flash import mostrar_flash

engine = get_engine()
usuario = auth.requerir_login(rol_requerido=auth.ROLES_OPERACION)

st.markdown("<h1 style='text-align:center;'>📋 Seguimiento OT</h1>", unsafe_allow_html=True)
mostrar_flash()

estados = ["Todas"] + list(ot.ESTADO_LABEL.values())
estado_sel = st.selectbox("Estado", options=estados, key="seguimiento_estado")
estado_key = None
if estado_sel != "Todas":
    estado_key = {v: k for k, v in ot.ESTADO_LABEL.items()}[estado_sel]

tabla = ot.ots_todas(engine, estado=estado_key)
if tabla.empty:
    st.info("No hay OTs para mostrar.")
else:
    tabla_mostrar = tabla.copy()
    tabla_mostrar["tipo_trabajo"] = tabla_mostrar["tipo_trabajo"].map(ot.TIPO_TRABAJO_LABEL)
    tabla_mostrar["estado"] = tabla_mostrar["estado"].map(ot.ESTADO_LABEL)
    tabla_mostrar["turno"] = tabla_mostrar["turno"].map(ot.TURNO_LABEL).fillna("—")
    tabla_mostrar["fecha_programada"] = tabla_mostrar["fecha_programada"].fillna("—")
    st.dataframe(
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
    )
