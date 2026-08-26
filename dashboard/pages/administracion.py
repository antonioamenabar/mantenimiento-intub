"""Administración - Intub

Página compartida por "admin" y "supervisor", con capacidades distintas:
  - Cuentas de Supervisor: crear/desactivar/restablecer contraseña --
    exclusivo de "admin" (nadie más puede crear otra cuenta de gestión).
  - Mecánicos y talleres externos: crear/desactivar/restablecer
    contraseña -- lo puede hacer tanto "admin" como "supervisor".
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from src import auth, ordenes_trabajo as ot
from src.bootstrap import get_engine
from src.flash import flash, mostrar_flash

engine = get_engine()
usuario = auth.requerir_login(rol_requerido=auth.ROLES_OPERACION)
es_admin = usuario["rol"] == "admin"

st.markdown("<h1 style='text-align:center;'>🔑 Administración</h1>", unsafe_allow_html=True)
mostrar_flash()

# ---------------------------------------------------------------------------
# Cuentas de Supervisor -- solo "admin"
# ---------------------------------------------------------------------------
if es_admin:
    st.markdown("### Cuentas de Supervisor")
    st.markdown("#### Crear cuenta")
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
                    engine, username=username_nuevo, password=password_nuevo, nombre=nombre_nuevo,
                )
                flash("success", f"{nombre_nuevo} (Supervisor) creado.")
                st.rerun()
            except Exception as exc:  # noqa: BLE001 -- lo más probable es username duplicado
                st.error(f"No se pudo crear la cuenta: {exc}")

    st.markdown("#### Cuentas existentes")
    cuentas = auth.usuarios_de_gestion(engine)
    if cuentas.empty:
        st.info("Todavía no hay ninguna cuenta de Supervisor.")
    else:
        cuentas_mostrar = cuentas.copy()
        cuentas_mostrar["activo"] = cuentas_mostrar["activo"].map({True: "Sí", False: "No"})
        st.dataframe(
            cuentas_mostrar[["nombre", "username", "activo", "created_at"]].rename(columns={
                "nombre": "Nombre", "username": "Usuario", "activo": "Activo", "created_at": "Creado",
            }),
            hide_index=True, width="content",
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

            st.markdown("###### Restablecer contraseña")
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

    st.divider()

# ---------------------------------------------------------------------------
# Mecánicos y talleres externos -- "admin" y "supervisor"
# ---------------------------------------------------------------------------
st.markdown("### Mecánicos y talleres externos")
st.markdown("#### Agregar mecánico interno o taller externo")
# Sin st.form: el checkbox "crear_acceso" necesita disparar un rerun
# inmediato para mostrar/ocultar los campos de usuario/contraseña, y los
# widgets dentro de un st.form no rerenderizan hasta enviarlo.
tipo = st.radio(
    "Tipo", options=["interno", "externo"],
    format_func=lambda t: "Mecánico interno" if t == "interno" else "Taller externo",
    horizontal=True, key="nuevo_mec_tipo",
)
nombre = st.text_input("Nombre", key="nuevo_mec_nombre")
contacto = st.text_input("Contacto (email y/o teléfono)", key="nuevo_mec_contacto")
crear_acceso = False
username_mec_nuevo = password_mec_nuevo = ""
if tipo == "interno":
    crear_acceso = st.checkbox("Darle su propia sesión para que complete sus OTs", key="nuevo_mec_crear_acceso")
    if crear_acceso:
        col_mu, col_mp = st.columns(2)
        with col_mu:
            username_mec_nuevo = st.text_input("Usuario para iniciar sesión", key="nuevo_mec_username")
        with col_mp:
            password_mec_nuevo = st.text_input("Contraseña inicial", type="password", key="nuevo_mec_password")
guardar_mec = st.button("Guardar", type="primary", key="nuevo_mec_guardar")

if guardar_mec:
    if not nombre:
        st.warning("Falta el nombre.")
    elif tipo == "externo" and not contacto:
        st.warning("Un taller externo necesita un email de contacto para poder enviarle OTs.")
    elif crear_acceso and not (username_mec_nuevo and password_mec_nuevo):
        st.warning("Falta usuario o contraseña para la sesión del mecánico.")
    else:
        usuario_id_mec = None
        if crear_acceso:
            usuario_id_mec = auth.crear_usuario_mecanico(engine, username_mec_nuevo, password_mec_nuevo, nombre)
        ot.guardar_mecanico_taller(engine, id=None, tipo=tipo, nombre=nombre, contacto=contacto, usuario_id=usuario_id_mec)
        flash("success", f"{nombre} agregado.")
        st.rerun()

st.markdown("#### Mecánicos y talleres activos")
activos = ot.mecanicos_talleres_activos(engine)
if activos.empty:
    st.info("Todavía no hay ninguno registrado.")
else:
    activos_mostrar = activos.copy()
    activos_mostrar["tipo"] = activos_mostrar["tipo"].map({"interno": "Mecánico interno", "externo": "Taller externo"})
    activos_mostrar["tiene_sesión"] = activos["usuario_id"].notna().map({True: "Sí", False: "No"})
    st.dataframe(
        activos_mostrar[["nombre", "tipo", "contacto", "tiene_sesión"]].rename(
            columns={"nombre": "Nombre", "tipo": "Tipo", "contacto": "Contacto"}
        ),
        hide_index=True, width="content",
    )
    col_desact_mec, col_boton_mec = st.columns([3, 1])
    with col_desact_mec:
        a_desactivar_mec = st.selectbox(
            "Desactivar", options=activos["id"].tolist(),
            format_func=lambda i: activos.set_index("id").loc[i, "nombre"], key="mec_desactivar_sel",
            label_visibility="collapsed",
        )
    with col_boton_mec:
        if st.button("Desactivar", key="mec_desactivar_btn"):
            ot.desactivar_mecanico_taller(engine, a_desactivar_mec)
            st.rerun()

    st.markdown("###### Restablecer contraseña de un mecánico")
    con_sesion = activos[activos["usuario_id"].notna()]
    if con_sesion.empty:
        st.caption("Ningún mecánico interno tiene sesión propia todavía.")
    else:
        nombre_por_mec_id = dict(zip(con_sesion["id"], con_sesion["nombre"]))
        col_mec, col_pass, col_reset = st.columns([2, 2, 1])
        with col_mec:
            mec_reset_id = st.selectbox(
                "Mecánico", options=con_sesion["id"].tolist(),
                format_func=lambda i: nombre_por_mec_id.get(i, i), key="mec_reset_sel",
            )
        with col_pass:
            pass_nueva_mec = st.text_input("Nueva contraseña", type="password", key="mec_reset_pass")
        with col_reset:
            st.markdown("<div style='height:1.7rem'></div>", unsafe_allow_html=True)  # alinea con los otros campos
            if st.button("Restablecer", key="mec_reset_btn"):
                if not pass_nueva_mec:
                    st.warning("Escribe una contraseña.")
                else:
                    usuario_id_reset = int(con_sesion.set_index("id").loc[mec_reset_id, "usuario_id"])
                    auth.cambiar_password(engine, usuario_id_reset, pass_nueva_mec)
                    flash("success", f"Contraseña de {nombre_por_mec_id.get(mec_reset_id)} restablecida.")
                    st.rerun()
