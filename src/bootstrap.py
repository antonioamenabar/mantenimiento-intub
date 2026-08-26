"""Arranque compartido por todas las páginas del dashboard/software: crea
las tablas si no existen y siembra catálogos/usuario inicial. Usa
`st.cache_resource` para que corra una sola vez por proceso del servidor,
sin importar desde qué página (Inicio, Dashboard, Software de Mantenimiento,
Mis OTs) se entre primero.
"""
import streamlit as st

from src import db, planificacion, auth, ot_checklist


@st.cache_resource
def get_engine():
    engine = db.init_db()
    planificacion.seed_catalogo_y_reglas(engine)
    planificacion.seed_componentes_conocidos_si_vacio(engine)
    auth.seed_usuarios_iniciales(engine)
    ot_checklist.seed_checklist_catalogo(engine)
    return engine
