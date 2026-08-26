"""Administración - Intub

Página exclusiva del rol "admin": crea y administra las cuentas de Jefe
de Mantenimiento / Supervisor (ambos roles tienen exactamente las mismas
capacidades sobre el Software de Mantenimiento -- crear/cancelar OTs,
administrar mecánicos y talleres -- la diferencia es solo de cargo). El
"admin" no opera OTs, solo administra estas cuentas.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from src import auth
from src.bootstrap import get_engine
from src.flash import flash, mostrar_flash

st.set_page_config(page_title="Administración - Intub", layout="wide")

engine = get_engine()
usuario = auth.requerir_login(rol_requerido="admin")

st.markdown("<h1 style='text-align:center;'>🔑 Administración</h1>", unsafe_allow_html=True)
mostrar_flash()

st.markdown("#### Crear cuenta de Jefe o Supervisor")
rol_nuevo = st.radio(
    "Rol", options=list(auth.ROLES_GESTION), format_func=lambda r: auth.ROL_LABEL[r],
    horizontal=True, key="nuevo_gestion_rol",
)
nombre_nuevo = st.text_input("Nombre", key="nuevo_gestion_nombre")
col_u, col_p = st.columns(2)
with col_u:
    username_nuevo = st.text_input("Usuario para iniciar sesión", key="nuevo_gestion_username")
with col_p:
    password_nuevo = st.text_input("Contraseña inicial", type="password", key="nuevo_gestion_password")

if st.button("Crear cuenta", type="primary", key="nuevo_gestion_guardar"):
    if not nombre_nuevo or not username_nuevo or not password_nuevo:
        st.warning("Faltan datos -- nombre, usuario y contraseña son obligatorios.")
    else:
        try:
            auth.crear_usuario_gestion(
                engine, username=username_nuevo, password=password_nuevo,
                nombre=nombre_nuevo, rol=rol_nuevo,
            )
            flash("success", f"{nombre_nuevo} ({auth.ROL_LABEL[rol_nuevo]}) creado.")
            st.rerun()
        except Exception as exc:  # noqa: BLE001 -- lo más probable es username duplicado
            st.error(f"No se pudo crear la cuenta: {exc}")

st.markdown("#### Cuentas de Jefe / Supervisor")
cuentas = auth.usuarios_de_gestion(engine)
if cuentas.empty:
    st.info("Todavía no hay ninguna cuenta.")
else:
    cuentas_mostrar = cuentas.copy()
    cuentas_mostrar["rol"] = cuentas_mostrar["rol"].map(auth.ROL_LABEL)
    cuentas_mostrar["activo"] = cuentas_mostrar["activo"].map({True: "Sí", False: "No"})
    st.dataframe(
        cuentas_mostrar[["nombre", "username", "rol", "activo", "created_at"]].rename(columns={
            "nombre": "Nombre", "username": "Usuario", "rol": "Rol", "activo": "Activo", "created_at": "Creado",
        }),
        hide_index=True, width="stretch",
    )

    activas = cuentas[cuentas["activo"]]
    if not activas.empty:
        col_desact, col_boton = st.columns([3, 1])
        with col_desact:
            a_desactivar = st.selectbox(
                "Desactivar", options=activas["id"].tolist(),
                format_func=lambda i: activas.set_index("id").loc[i, "nombre"], key="gestion_desactivar_sel",
                label_visibility="collapsed",
            )
        with col_boton:
            if st.button("Desactivar", key="gestion_desactivar_btn"):
                auth.desactivar_usuario(engine, a_desactivar)
                flash("success", "Cuenta desactivada.")
                st.rerun()

        st.markdown("#### Restablecer contraseña")
        nombre_por_id = dict(zip(activas["id"], activas["nombre"]))
        col_cta, col_pass, col_reset = st.columns([2, 2, 1])
        with col_cta:
            cta_reset_id = st.selectbox(
                "Cuenta", options=activas["id"].tolist(),
                format_func=lambda i: nombre_por_id.get(i, i), key="gestion_reset_sel",
            )
        with col_pass:
            pass_nueva = st.text_input("Nueva contraseña", type="password", key="gestion_reset_pass")
        with col_reset:
            st.markdown("<div style='height:1.7rem'></div>", unsafe_allow_html=True)  # alinea con los otros campos
            if st.button("Restablecer", key="gestion_reset_btn"):
                if not pass_nueva:
                    st.warning("Escribe una contraseña.")
                else:
                    auth.cambiar_password(engine, cta_reset_id, pass_nueva)
                    flash("success", f"Contraseña de {nombre_por_id.get(cta_reset_id)} restablecida.")
                    st.rerun()
