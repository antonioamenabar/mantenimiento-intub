"""Inicio - Software y Dashboard de Mantenimiento (Intub)

Página de entrada: inicio de sesión. Una vez logueado, el menú de la
izquierda (páginas de Streamlit) muestra:
  - Dashboard                  -- solo lectura, roles "jefe"/"supervisor"
  - Software de Mantenimiento  -- crear/asignar/cancelar OTs, "jefe"/"supervisor"
  - Mis OTs                    -- ver y completar OTs asignadas, todos menos "admin"
  - Hoja de Vida                -- historial por camión, "jefe"/"supervisor"
  - Administración              -- crea cuentas de Jefe/Supervisor, solo "admin"

Uso:
    streamlit run dashboard/app.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from src import auth
from src.bootstrap import get_engine

st.set_page_config(page_title="Mantenimiento Intub", layout="centered")

engine = get_engine()

st.markdown("<h1 style='text-align:center;'>🚛 Mantenimiento Intub</h1>", unsafe_allow_html=True)

usuario = auth.usuario_actual()

if usuario is None:
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
        "¿Primera vez? Los usuarios iniciales son **jefe** / **cambiar123** (Jefe de Mantenimiento) "
        "y **admin** / **cambiar123** (Administrador, crea cuentas de Jefe/Supervisor) -- "
        "cámbialas en \"Mi cuenta\" apenas entres."
    )

else:
    st.success(f"Sesión iniciada como **{usuario['nombre']}** ({auth.ROL_LABEL.get(usuario['rol'], usuario['rol'])}).")
    st.write("Usa el menú de la izquierda para navegar:")
    if usuario["rol"] in auth.ROLES_GESTION:
        st.markdown(
            "- **Dashboard** -- vista general de Inspecciones, Fallas y Mantenimiento Programado.\n"
            "- **Software de Mantenimiento** -- crear, asignar y cancelar Órdenes de Trabajo, "
            "administrar mecánicos y talleres.\n"
            "- **Mis OTs** -- seguimiento de todas las OTs y su estado.\n"
            "- **Hoja de Vida** -- historial completo de cada camión, con Certificado de "
            "Mantención descargable por registro."
        )
    elif usuario["rol"] == "admin":
        st.markdown("- **Administración** -- crear y administrar cuentas de Jefe de Mantenimiento / Supervisor.")
    else:
        st.markdown("- **Mis OTs** -- las Órdenes de Trabajo que te asignaron, para marcarlas completadas.")

    with st.expander("Mi cuenta"):
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

    if st.button("Cerrar sesión"):
        del st.session_state["usuario"]
        st.rerun()
