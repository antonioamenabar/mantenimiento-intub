"""Software de Mantenimiento - Intub

Acá se CREA y ASIGNA el trabajo (distinto del Dashboard, que solo muestra
estado). Tres secciones: crear una OT nueva, seguimiento de todas las OTs,
y administrar mecánicos internos / talleres externos.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from src import auth, planificacion, ordenes_trabajo as ot
from src.bootstrap import get_engine
from src.flash import flash, mostrar_flash
from src.queries import opciones_patentes, PRIORIDAD_LABEL

st.set_page_config(page_title="Software de Mantenimiento - Intub", layout="wide")

engine = get_engine()
usuario = auth.requerir_login(rol_requerido="jefe")

st.markdown("<h1 style='text-align:center;'>🧰 Software de Mantenimiento</h1>", unsafe_allow_html=True)
mostrar_flash()


@st.dialog("Detalle del ticket")
def _dialog_detalle_falla(ticket_id: str):
    detalle = ot.falla_por_id(engine, ticket_id)
    if not detalle:
        st.info("No se encontró el ticket (puede que ya se haya cerrado en Datascope).")
    else:
        st.markdown(f"**#{detalle['code']}** — {PRIORIDAD_LABEL.get(detalle['priority'], detalle['priority'])}")
        descripcion = (detalle["description"] or detalle["name"] or "").strip() or "(sin descripción)"
        st.markdown(f"**Descripción:** {descripcion}")
        st.markdown(f"**Creado por:** {detalle['creator_name'] or '—'}")
        st.markdown(f"**Fecha de creación:** {detalle['creation_date'] or '—'}")
        st.markdown(f"**Estado:** {detalle['status'] or '—'}")
        st.caption(
            "Datascope no expone fotos ni comentarios por API, y su sitio no cambia de URL al "
            "abrir un ticket -- si necesitas ver una foto adjunta, ábrelo ahí y búscalo por el N°."
        )
        st.link_button("Abrir Tickets en Datascope ↗", ot.DATASCOPE_TICKETS_URL)
    if st.button("Cerrar", key="cerrar_detalle_falla_ot"):
        st.query_params.clear()
        st.rerun()


def _revisar_query_params_falla_ot():
    valor = st.query_params.get("ot_falla_detalle")
    if valor:
        _dialog_detalle_falla(valor)


def _tabla_gris_html(filas_html: str, encabezados: list[str]) -> str:
    """Tabla de solo lectura, en gris, para lo que ya está asignado a otra
    OT en curso -- no seleccionable, a propósito, para que no se pueda
    volver a asignar dos veces lo mismo.
    """
    head = "".join(f"<th>{h}</th>" for h in encabezados)
    return f"""
    <style>
      .tabla-gris {{ border-collapse: collapse; width: 100%; font-size: 13px; color: #888; }}
      .tabla-gris th, .tabla-gris td {{
        border: 1px solid rgba(128,128,128,0.25); padding: 4px 8px; text-align: center;
        background: rgba(128,128,128,0.10);
      }}
      .tabla-gris td.izq {{ text-align: left; }}
      .tabla-gris thead th {{ font-weight: 600; }}
    </style>
    <table class="tabla-gris">
      <thead><tr>{head}</tr></thead>
      <tbody>{filas_html}</tbody>
    </table>
    """


_revisar_query_params_falla_ot()

tab_crear, tab_seguimiento, tab_equipo = st.tabs(
    ["➕ Crear Nueva OT", "📋 Seguimiento de OTs", "👷 Mecánicos y talleres"]
)


# ---------------------------------------------------------------------------
# Crear Nueva OT
# ---------------------------------------------------------------------------
with tab_crear:
    todas_patentes = opciones_patentes(engine)
    nombre_por_patente = dict(zip(todas_patentes["patente"], todas_patentes["nombre_corto"]))

    asignables = ot.mecanicos_talleres_activos(engine)
    if asignables.empty:
        st.warning(
            "Todavía no hay mecánicos internos ni talleres externos registrados. "
            "Ve a la pestaña **Mecánicos y talleres** y agrega al menos uno antes de crear una OT."
        )
    else:
        col1, col2 = st.columns(2)
        with col1:
            patente = st.selectbox(
                "Camión", options=todas_patentes["patente"].tolist(),
                format_func=lambda p: f"{nombre_por_patente.get(p, p)} ({p})",
                key="ot_patente",
            )
        with col2:
            etiqueta_asignado = dict(zip(
                asignables["id"],
                asignables["nombre"] + " — " + asignables["tipo"].map({"interno": "mecánico interno", "externo": "taller externo"}),
            ))
            asignado_id = st.selectbox(
                "Asignar a", options=asignables["id"].tolist(),
                format_func=lambda i: etiqueta_asignado.get(i, i), key="ot_asignado_id",
            )

        st.caption(
            "Una misma OT puede llevar trabajo de más de un tipo -- marca lo que corresponda "
            "en cada sección de abajo."
        )
        items_sel = []

        with st.expander("🔍 Inspección", expanded=False):
            subtipos_sel = st.multiselect(
                "Tipo de inspección", options=ot.SUBTIPOS_INSPECCION, key="ot_subtipos_inspeccion",
            )
            items_sel += [{"tipo_item": "inspeccion", "referencia": s, "descripcion": s} for s in subtipos_sel]

        with st.expander("⚠️ Fallas", expanded=False):
            fallas = ot.fallas_para_ot(engine, patente)
            asignadas_falla = ot.fallas_asignadas(engine, patente)  # {ticket_id: numero_ot}
            if fallas.empty:
                st.info("Este camión no tiene fallas abiertas en Datascope.")
            else:
                ya_asignada = fallas["id"].astype(str).isin(asignadas_falla.keys())
                fallas_disp = fallas[~ya_asignada].reset_index(drop=True)
                fallas_asig = fallas[ya_asignada]

                if fallas_disp.empty:
                    st.info("Todas las fallas abiertas de este camión ya están asignadas a otra OT en curso.")
                else:
                    st.caption(
                        "Ordenadas de más crítica y antigua, a menos. Marca el ✅ de la primera "
                        "columna para incluirla en la OT."
                    )
                    tabla_mostrar = fallas_disp.copy()
                    tabla_mostrar["priority"] = tabla_mostrar["priority"].map(PRIORIDAD_LABEL).fillna(tabla_mostrar["priority"])
                    tabla_mostrar = tabla_mostrar.rename(columns={
                        "code": "N°", "descripcion": "Descripción", "priority": "Criticidad", "dias": "Antigüedad (días)",
                    })
                    # La key incluye la patente a propósito: la selección de
                    # st.dataframe es por índice de fila, no por valor -- si
                    # no se reinicia al cambiar de camión, podría quedar
                    # "seleccionada" una fila de otro camión por error.
                    seleccion_fallas = st.dataframe(
                        tabla_mostrar[["N°", "Descripción", "Criticidad", "Antigüedad (días)"]],
                        hide_index=True, width="stretch",
                        on_select="rerun", selection_mode="multi-row", key=f"ot_fallas_tabla_{patente}",
                    )
                    filas_sel = seleccion_fallas["selection"]["rows"] if seleccion_fallas else []
                    fallas_sel_df = fallas_disp.iloc[filas_sel]
                    items_sel += [
                        {
                            "tipo_item": "ticket", "referencia": str(r["id"]),
                            "descripcion": f"#{r['code']} — {r['descripcion']}",
                        }
                        for _, r in fallas_sel_df.iterrows()
                    ]

                if not fallas_asig.empty:
                    st.caption("Ya asignadas a otra OT en curso -- no se pueden volver a asignar:")
                    filas_html = "".join(
                        "<tr>"
                        f"<td>#{r['code']}</td>"
                        f"<td class='izq'>{r['descripcion']}</td>"
                        f"<td>{PRIORIDAD_LABEL.get(r['priority'], r['priority'])}</td>"
                        f"<td>{asignadas_falla.get(str(r['id']), '—')}</td>"
                        "</tr>"
                        for _, r in fallas_asig.iterrows()
                    )
                    st.html(_tabla_gris_html(filas_html, ["N°", "Descripción", "Criticidad", "OT asignada"]))

                with st.popover("🔍 Ver detalle de un ticket"):
                    etiqueta_falla = dict(zip(
                        fallas["id"], "#" + fallas["code"].astype(str) + " — " + fallas["descripcion"],
                    ))
                    ticket_ver = st.selectbox(
                        "Ticket", options=fallas["id"].tolist(),
                        format_func=lambda i: etiqueta_falla.get(i, i), key="ot_falla_ver_sel",
                        label_visibility="collapsed",
                    )
                    if st.button("Ver detalle", key="ot_falla_ver_btn"):
                        _dialog_detalle_falla(ticket_ver)

        with st.expander("🛠️ Mantenimiento Programado", expanded=False):
            items_estado = ot.items_mantenimiento_para_ot(engine, patente)
            asignados_mant = ot.items_mantenimiento_asignados(engine, patente)  # {item_key: numero_ot}

            ya_asignado = items_estado["item_key"].isin(asignados_mant.keys())
            items_disp = items_estado[~ya_asignado].reset_index(drop=True)
            items_asig = items_estado[ya_asignado]

            if items_disp.empty:
                st.info("Todos los componentes de este camión ya están asignados a otra OT en curso.")
            else:
                items_disp_mostrar = items_disp.copy()
                items_disp_mostrar["categoria"] = items_disp_mostrar["categoria"].map(planificacion.CATEGORIA_LABEL)
                items_disp_mostrar["horas_venc"] = items_disp_mostrar["horas_venc"].apply(
                    lambda h: "Sin dato" if h is None else f"{h:.0f}"
                )
                st.caption("Marca el ✅ de la primera columna para incluir ese componente en la OT.")
                # Misma razón que en Fallas: la key incluye la patente para
                # que la selección se reinicie al cambiar de camión.
                seleccion_mant = st.dataframe(
                    items_disp_mostrar[["categoria", "nombre", "horas_venc"]].rename(
                        columns={"categoria": "Grupo", "nombre": "Componente", "horas_venc": "Horas para el vencimiento"}
                    ),
                    hide_index=True, width="stretch",
                    on_select="rerun", selection_mode="multi-row", key=f"ot_mant_tabla_{patente}",
                )
                filas_sel_mant = seleccion_mant["selection"]["rows"] if seleccion_mant else []
                items_mant_sel_df = items_disp.iloc[filas_sel_mant]
                items_sel += [
                    {"tipo_item": "item_key", "referencia": r["item_key"], "descripcion": r["nombre"]}
                    for _, r in items_mant_sel_df.iterrows()
                ]

            if not items_asig.empty:
                st.caption("Ya asignados a otra OT en curso -- no se pueden volver a asignar:")
                filas_html = "".join(
                    "<tr>"
                    f"<td class='izq'>{planificacion.CATEGORIA_LABEL.get(r['categoria'], r['categoria'])}</td>"
                    f"<td class='izq'>{r['nombre']}</td>"
                    f"<td>{asignados_mant.get(r['item_key'], '—')}</td>"
                    "</tr>"
                    for _, r in items_asig.iterrows()
                )
                st.html(_tabla_gris_html(filas_html, ["Grupo", "Componente", "OT asignada"]))

        st.divider()

        if not items_sel:
            st.caption("Selecciona al menos un ítem para poder ver el borrador.")
        else:
            if st.button("Ver borrador de la OT", key="ot_ver_borrador"):
                st.session_state["ot_borrador"] = {
                    "patente": patente, "asignado_id": asignado_id, "items": items_sel,
                }

        borrador = st.session_state.get("ot_borrador")
        if borrador:
            st.markdown("#### Borrador de la OT")
            asignado_nombre = etiqueta_asignado.get(borrador["asignado_id"], borrador["asignado_id"])
            tipo_resumen = ot.TIPO_TRABAJO_LABEL[ot.tipo_trabajo_resumen(borrador["items"])]
            etiqueta_categoria = {"inspeccion": "Inspección", "ticket": "Fallas", "item_key": "Mantenimiento Programado"}
            with st.container(border=True):
                st.markdown(f"**Camión:** {nombre_por_patente.get(borrador['patente'], borrador['patente'])} ({borrador['patente']})")
                st.markdown(f"**Asignado a:** {asignado_nombre}")
                st.markdown(f"**Tipo de trabajo:** {tipo_resumen}")
                st.markdown("**Ítems:**")
                for categoria in ("inspeccion", "ticket", "item_key"):
                    del_categoria = [it for it in borrador["items"] if it["tipo_item"] == categoria]
                    if not del_categoria:
                        continue
                    st.markdown(f"*{etiqueta_categoria[categoria]}:*")
                    for it in del_categoria:
                        st.markdown(f"- {it['descripcion']}")

            col_aprobar, col_editar = st.columns(2)
            with col_aprobar:
                if st.button("✅ Aprobar y enviar", type="primary", key="ot_aprobar"):
                    resultado = ot.crear_y_enviar_ot(
                        engine, patente=borrador["patente"],
                        asignado_id=borrador["asignado_id"], items=borrador["items"],
                        creado_por=usuario["nombre"],
                    )
                    mensaje = f"OT {resultado['numero_ot']} creada y enviada."
                    if resultado["email_enviado"]:
                        mensaje += " Email enviado al taller externo."
                        flash("success", mensaje)
                    elif resultado["email_error"]:
                        flash("warning", f"{mensaje} La OT quedó creada, pero no se pudo enviar el email: {resultado['email_error']}")
                    else:
                        flash("success", mensaje)
                    del st.session_state["ot_borrador"]
                    st.rerun()
            with col_editar:
                if st.button("✏️ Seguir editando", key="ot_editar"):
                    del st.session_state["ot_borrador"]
                    st.rerun()


# ---------------------------------------------------------------------------
# Seguimiento de OTs
# ---------------------------------------------------------------------------
with tab_seguimiento:
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
        st.dataframe(
            tabla_mostrar[[
                "numero_ot", "patente", "tipo_trabajo", "asignado_nombre", "asignado_tipo",
                "estado", "creado_at", "completado_at",
            ]].rename(columns={
                "numero_ot": "OT", "patente": "Camión", "tipo_trabajo": "Tipo",
                "asignado_nombre": "Asignado a", "asignado_tipo": "Tipo asignado",
                "estado": "Estado", "creado_at": "Creada", "completado_at": "Completada",
            }),
            hide_index=True, width="stretch",
        )


# ---------------------------------------------------------------------------
# Mecánicos y talleres
# ---------------------------------------------------------------------------
with tab_equipo:
    st.markdown("#### Agregar mecánico interno o taller externo")
    # Sin st.form: el checkbox "crear_acceso" necesita disparar un rerun
    # inmediato para mostrar/ocultar los campos de usuario/contraseña, y
    # los widgets dentro de un st.form no rerenderizan hasta enviarlo.
    tipo = st.radio(
        "Tipo", options=["interno", "externo"],
        format_func=lambda t: "Mecánico interno" if t == "interno" else "Taller externo",
        horizontal=True, key="nuevo_mec_tipo",
    )
    nombre = st.text_input("Nombre", key="nuevo_mec_nombre")
    contacto = st.text_input("Contacto (email y/o teléfono)", key="nuevo_mec_contacto")
    crear_acceso = False
    username_nuevo = password_nuevo = ""
    if tipo == "interno":
        crear_acceso = st.checkbox("Darle su propia sesión para que complete sus OTs", key="nuevo_mec_crear_acceso")
        if crear_acceso:
            col_u, col_p = st.columns(2)
            with col_u:
                username_nuevo = st.text_input("Usuario para iniciar sesión", key="nuevo_mec_username")
            with col_p:
                password_nuevo = st.text_input("Contraseña inicial", type="password", key="nuevo_mec_password")
    guardar = st.button("Guardar", type="primary", key="nuevo_mec_guardar")

    if guardar:
        if not nombre:
            st.warning("Falta el nombre.")
        elif tipo == "externo" and not contacto:
            st.warning("Un taller externo necesita un email de contacto para poder enviarle OTs.")
        elif crear_acceso and not (username_nuevo and password_nuevo):
            st.warning("Falta usuario o contraseña para la sesión del mecánico.")
        else:
            usuario_id = None
            if crear_acceso:
                usuario_id = auth.crear_usuario_mecanico(engine, username_nuevo, password_nuevo, nombre)
            ot.guardar_mecanico_taller(engine, id=None, tipo=tipo, nombre=nombre, contacto=contacto, usuario_id=usuario_id)
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
            hide_index=True, width="stretch",
        )
        col_desact, col_boton = st.columns([3, 1])
        with col_desact:
            a_desactivar = st.selectbox(
                "Desactivar", options=activos["id"].tolist(),
                format_func=lambda i: activos.set_index("id").loc[i, "nombre"], key="mec_desactivar_sel",
                label_visibility="collapsed",
            )
        with col_boton:
            if st.button("Desactivar", key="mec_desactivar_btn"):
                ot.desactivar_mecanico_taller(engine, a_desactivar)
                st.rerun()

        st.markdown("#### Restablecer contraseña de un mecánico")
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
                pass_nueva = st.text_input("Nueva contraseña", type="password", key="mec_reset_pass")
            with col_reset:
                st.markdown("<div style='height:1.7rem'></div>", unsafe_allow_html=True)  # alinea con los otros campos
                if st.button("Restablecer", key="mec_reset_btn"):
                    if not pass_nueva:
                        st.warning("Escribe una contraseña.")
                    else:
                        usuario_id_reset = int(con_sesion.set_index("id").loc[mec_reset_id, "usuario_id"])
                        auth.cambiar_password(engine, usuario_id_reset, pass_nueva)
                        flash("success", f"Contraseña de {nombre_por_mec_id.get(mec_reset_id)} restablecida.")
                        st.rerun()
