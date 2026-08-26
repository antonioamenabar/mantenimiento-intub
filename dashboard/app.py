"""Inicio - Software y Dashboard de Mantenimiento (Intub)

Entrada única de la app: login, y desde acá se arma el menú de
navegación (`st.navigation`) según el rol -- "admin" y "supervisor" ven
todo (Dashboard, Software: Crear OT / Seguimiento OT / Hoja de Vida /
Programa de Mantención, Mis OTs, Administración); "mecanico" ve solo
"Mis OTs". El usuario logueado, y "Mi cuenta" (cambiar contraseña, cerrar
sesión), quedan en un popover arriba a la derecha, no como página del
menú -- por eso este archivo ("app") ya no aparece en la lista de la
izquierda como una página más.

`st.set_page_config` vive acá y solo acá (una app con navegación
programática no puede llamarlo de nuevo dentro de cada página) -- el
título de la pestaña de cada página se controla con `st.Page(title=...)`.

Uso:
    streamlit run dashboard/app.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from src import auth
from src.bootstrap import get_engine

PAGES_DIR = Path(__file__).resolve().parent / "pages"

st.set_page_config(page_title="Mantenimiento Intub", page_icon="🚛", layout="wide")

engine = get_engine()
usuario = auth.usuario_actual()

if usuario is None:
    st.markdown("<h1 style='text-align:center;'>🚛 Mantenimiento Intub</h1>", unsafe_allow_html=True)
    _, col_centro, _ = st.columns([1, 1, 1])
    with col_centro:
        st.subheader("Iniciar sesión")
        with st.form("form_login"):
            username = st.text_input("Usuario")
            password = st.text_input("Contraseña", type="password")
            entrar = st.form_submit_button("Entrar", type="primary")
        if entrar:
            encontrado = auth.verificar_login(engine, username, password)
            if encontrado:
                st.session_state["usuario"] = encontrado
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos.")
        st.caption(
            "¿Primera vez? Los usuarios iniciales son **supervisor** / **cambiar123** y "
            "**admin** / **cambiar123** (crea cuentas de Supervisor) -- cámbialas apenas "
            "entres, en el menú de tu nombre arriba a la derecha."
        )
    st.stop()

# --- Usuario logueado: título + "Mi cuenta" (arriba a la derecha) ---
col_titulo, col_cuenta = st.columns([6, 2], vertical_alignment="center")
with col_titulo:
    st.markdown("<h2 style='margin:0;'>🚛 Mantenimiento Intub</h2>", unsafe_allow_html=True)
with col_cuenta:
    with st.popover(f"👤 {usuario['nombre']}"):
        st.caption(auth.ROL_LABEL.get(usuario["rol"], usuario["rol"]))
        with st.form("form_cambiar_password"):
            nueva = st.text_input("Nueva contraseña", type="password")
            confirmar = st.text_input("Repetir contraseña", type="password")
            guardar = st.form_submit_button("Cambiar contraseña")
        if guardar:
            if not nueva:
                st.warning("Escribe una contraseña.")
            elif nueva != confirmar:
                st.warning("Las dos contraseñas no coinciden.")
            else:
                auth.cambiar_password(engine, usuario["id"], nueva)
                st.success("Contraseña actualizada.")
        st.divider()
        if st.button("Cerrar sesión", width="stretch"):
            del st.session_state["usuario"]
            st.rerun()

st.divider()

# --- Navegación según el rol ---
if usuario["rol"] == "mecanico":
    pages = {"": [st.Page(PAGES_DIR / "mis_ots.py", title="Mis OTs", icon="📝", default=True)]}
else:
    # "admin" y "supervisor" ven exactamente las mismas páginas -- la
    # única diferencia entre ambos vive DENTRO de Administración.
    pages = {
        "": [
            st.Page(PAGES_DIR / "dashboard.py", title="Dashboard", icon="🚛", default=True),
            st.Page(PAGES_DIR / "mis_ots.py", title="Mis OTs", icon="📝"),
            st.Page(PAGES_DIR / "administracion.py", title="Administración", icon="🔑"),
        ],
        "Software": [
            st.Page(PAGES_DIR / "crear_ot.py", title="Crear OT", icon="➕"),
            st.Page(PAGES_DIR / "seguimiento_ot.py", title="Seguimiento OT", icon="📋"),
            st.Page(PAGES_DIR / "hoja_de_vida.py", title="Hoja de Vida", icon="📖"),
            st.Page(PAGES_DIR / "programa_mantenimiento.py", title="Programa de Mantención", icon="🗓️"),
        ],
    }

st.navigation(pages, expanded=True).run()
