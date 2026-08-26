"""Software de Mantenimiento - Intub

Acá se CREA y ASIGNA el trabajo (distinto del Dashboard, que solo muestra
estado). Tres secciones: crear una OT nueva, seguimiento de todas las OTs,
y administrar mecánicos internos / talleres externos.
"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from src import auth, planificacion, ordenes_trabajo as ot
from src.bootstrap import get_engine
from src.flash import flash, mostrar_flash
from src.queries import opciones_patentes, PRIORIDAD_LABEL

st.set_page_config(page_title="Software de Mantenimiento - Intub", layout="wide")

engine = get_engine()
usuario = auth.requerir_login(rol_requerido=auth.ROLES_GESTION)

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
      .tabla-gris {{ border-collapse: collapse; width: auto; font-size: 13px; color: #888; }}
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
        col_fecha, col_turno, col_asignado = st.columns(3)
        with col_fecha:
            fecha_prog = st.date_input("Fecha", value=datetime.now().date(), key="ot_fecha")
        with col_turno:
            turno_sel = st.radio(
                "Turno", options=["diurno", "nocturno"], format_func=lambda t: ot.TURNO_LABEL[t],
                horizontal=True, key="ot_turno",
            )
        with col_asignado:
            etiqueta_asignado = dict(zip(
                asignables["id"],
                asignables["nombre"] + " — " + asignables["tipo"].map({"interno": "mecánico interno", "externo": "taller externo"}),
            ))
            asignados_ids = st.multiselect(
                "Asignar a", options=asignables["id"].tolist(),
                format_func=lambda i: etiqueta_asignado.get(i, i), key="ot_asignados_ids",
                help="Puede ir a más de uno a la vez -- por ejemplo, una pareja de mecánicos.",
            )

        st.caption(
            "Una misma OT puede llevar trabajo de más de un tipo, y de más de un camión -- agrega "
            "lo que corresponda en cada sección y después revisa el borrador."
        )

        # El "carrito" junta los ítems elegidos en las 3 secciones antes de
        # armar el borrador -- cada ítem lleva su propia patente, así una
        # OT puede combinar camiones distintos.
        carrito = st.session_state.setdefault("ot_carrito", [])

        with st.expander(f"🔍 Inspección", expanded=False):
            subtipos_sel = st.multiselect(
                "Tipo de inspección", options=ot.SUBTIPOS_INSPECCION, key="ot_insp_subtipos",
            )
            patentes_insp_sel = st.multiselect(
                "Camiones a los que aplica", options=todas_patentes["patente"].tolist(),
                format_func=lambda p: f"{nombre_por_patente.get(p, p)} ({p})", key="ot_insp_patentes",
            )
            if st.button("➕ Agregar al carrito", key="ot_insp_agregar"):
                if not subtipos_sel or not patentes_insp_sel:
                    st.warning("Elige al menos un tipo de inspección y un camión.")
                else:
                    agregados = 0
                    for patente_i in patentes_insp_sel:
                        for subtipo in subtipos_sel:
                            ya_existe = any(
                                it["tipo_item"] == "inspeccion" and it["referencia"] == subtipo and it["patente"] == patente_i
                                for it in carrito
                            )
                            if not ya_existe:
                                carrito.append({
                                    "tipo_item": "inspeccion", "referencia": subtipo,
                                    "descripcion": subtipo, "patente": patente_i,
                                })
                                agregados += 1
                    st.success(f"{agregados} ítem(s) agregado(s) al carrito.")
                    st.rerun()

        with st.expander("⚠️ Fallas", expanded=False):
            patente_falla_sel = st.selectbox(
                "Camión", options=todas_patentes["patente"].tolist(),
                format_func=lambda p: f"{nombre_por_patente.get(p, p)} ({p})", key="ot_falla_patente",
            )
            fallas = ot.fallas_para_ot(engine, patente_falla_sel)
            asignadas_falla = ot.fallas_asignadas(engine, patente_falla_sel)  # {ticket_id: numero_ot}
            en_carrito_falla = {
                it["referencia"] for it in carrito if it["tipo_item"] == "ticket" and it["patente"] == patente_falla_sel
            }
            if fallas.empty:
                st.info("Este camión no tiene fallas abiertas en Datascope.")
            else:
                ya_asignada = fallas["id"].astype(str).isin(asignadas_falla.keys()) | fallas["id"].astype(str).isin(en_carrito_falla)
                fallas_disp = fallas[~ya_asignada].reset_index(drop=True)
                fallas_asig = fallas[ya_asignada]

                if fallas_disp.empty:
                    st.info("No quedan fallas de este camión disponibles (ya asignadas o ya en el carrito).")
                else:
                    st.caption(
                        "Ordenadas de más crítica y antigua, a menos. Marca el ✅ de la primera "
                        "columna e inclúyelas en el carrito."
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
                        hide_index=True, width="content",
                        on_select="rerun", selection_mode="multi-row", key=f"ot_fallas_tabla_{patente_falla_sel}",
                    )
                    filas_sel = seleccion_fallas["selection"]["rows"] if seleccion_fallas else []
                    fallas_sel_df = fallas_disp.iloc[filas_sel]
                    if st.button("➕ Agregar seleccionadas al carrito", key="ot_falla_agregar"):
                        if fallas_sel_df.empty:
                            st.warning("No marcaste ninguna falla.")
                        else:
                            for _, r in fallas_sel_df.iterrows():
                                carrito.append({
                                    "tipo_item": "ticket", "referencia": str(r["id"]),
                                    "descripcion": f"#{r['code']} — {r['descripcion']}", "patente": patente_falla_sel,
                                })
                            st.success(f"{len(fallas_sel_df)} falla(s) agregada(s) al carrito.")
                            st.rerun()

                if not fallas_asig.empty:
                    st.caption("Ya asignadas a otra OT en curso, o ya en el carrito -- no se pueden agregar de nuevo:")
                    filas_html = "".join(
                        "<tr>"
                        f"<td>#{r['code']}</td>"
                        f"<td class='izq'>{r['descripcion']}</td>"
                        f"<td>{PRIORIDAD_LABEL.get(r['priority'], r['priority'])}</td>"
                        f"<td>{asignadas_falla.get(str(r['id'])) or 'En este carrito'}</td>"
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
            patente_mant_sel = st.selectbox(
                "Camión", options=todas_patentes["patente"].tolist(),
                format_func=lambda p: f"{nombre_por_patente.get(p, p)} ({p})", key="ot_mant_patente",
            )
            items_estado = ot.items_mantenimiento_para_ot(engine, patente_mant_sel)
            asignados_mant = ot.items_mantenimiento_asignados(engine, patente_mant_sel)  # {item_key: numero_ot}
            en_carrito_mant = {
                it["referencia"] for it in carrito if it["tipo_item"] == "item_key" and it["patente"] == patente_mant_sel
            }

            ya_asignado = items_estado["item_key"].isin(asignados_mant.keys()) | items_estado["item_key"].isin(en_carrito_mant)
            items_disp = items_estado[~ya_asignado].reset_index(drop=True)
            items_asig = items_estado[ya_asignado]

            if items_disp.empty:
                st.info("No quedan componentes de este camión disponibles (ya asignados o ya en el carrito).")
            else:
                items_disp_mostrar = items_disp.copy()
                items_disp_mostrar["categoria"] = items_disp_mostrar["categoria"].map(planificacion.CATEGORIA_LABEL)
                items_disp_mostrar["horas_venc"] = items_disp_mostrar["horas_venc"].apply(
                    lambda h: "Sin dato" if h is None else f"{h:.0f}"
                )
                st.caption("Marca el ✅ de la primera columna e inclúyelos en el carrito.")
                # Misma razón que en Fallas: la key incluye la patente para
                # que la selección se reinicie al cambiar de camión.
                seleccion_mant = st.dataframe(
                    items_disp_mostrar[["categoria", "nombre", "horas_venc"]].rename(
                        columns={"categoria": "Grupo", "nombre": "Componente", "horas_venc": "Horas para el vencimiento"}
                    ),
                    hide_index=True, width="content",
                    on_select="rerun", selection_mode="multi-row", key=f"ot_mant_tabla_{patente_mant_sel}",
                )
                filas_sel_mant = seleccion_mant["selection"]["rows"] if seleccion_mant else []
                items_mant_sel_df = items_disp.iloc[filas_sel_mant]
                if st.button("➕ Agregar seleccionados al carrito", key="ot_mant_agregar"):
                    if items_mant_sel_df.empty:
                        st.warning("No marcaste ningún componente.")
                    else:
                        for _, r in items_mant_sel_df.iterrows():
                            carrito.append({
                                "tipo_item": "item_key", "referencia": r["item_key"],
                                "descripcion": r["nombre"], "patente": patente_mant_sel,
                            })
                        st.success(f"{len(items_mant_sel_df)} componente(s) agregado(s) al carrito.")
                        st.rerun()

            if not items_asig.empty:
                st.caption("Ya asignados a otra OT en curso, o ya en el carrito -- no se pueden agregar de nuevo:")
                filas_html = "".join(
                    "<tr>"
                    f"<td class='izq'>{planificacion.CATEGORIA_LABEL.get(r['categoria'], r['categoria'])}</td>"
                    f"<td class='izq'>{r['nombre']}</td>"
                    f"<td>{asignados_mant.get(r['item_key']) or 'En este carrito'}</td>"
                    "</tr>"
                    for _, r in items_asig.iterrows()
                )
                st.html(_tabla_gris_html(filas_html, ["Grupo", "Componente", "OT asignada"]))

        st.divider()

        etiqueta_categoria = {"inspeccion": "Inspección", "ticket": "Fallas", "item_key": "Mantenimiento Programado"}

        if not carrito:
            st.caption("El carrito está vacío -- agrega ítems en las secciones de arriba.")
        else:
            st.markdown(f"#### Carrito ({len(carrito)} ítem(s))")
            for i, it in enumerate(carrito):
                nombre_camion = nombre_por_patente.get(it["patente"], it["patente"])
                col_item, col_quitar = st.columns([5, 1])
                with col_item:
                    st.markdown(f"**{etiqueta_categoria[it['tipo_item']]}** — {it['descripcion']} — {nombre_camion} ({it['patente']})")
                with col_quitar:
                    if st.button("🗑️", key=f"ot_carrito_quitar_{i}"):
                        carrito.pop(i)
                        st.rerun()

            if st.button("Ver borrador de la OT", key="ot_ver_borrador"):
                if not asignados_ids:
                    st.warning("Elige a quién asignar la OT (Asignar a, arriba) antes de ver el borrador.")
                else:
                    st.session_state["ot_borrador"] = list(carrito)

        borrador = st.session_state.get("ot_borrador")
        if borrador:
            st.markdown("#### Borrador de la OT")
            asignados_nombres = ", ".join(etiqueta_asignado.get(i, str(i)) for i in asignados_ids)
            tipo_resumen = ot.TIPO_TRABAJO_LABEL[ot.tipo_trabajo_resumen(borrador)]
            patentes_borrador = sorted({it["patente"] for it in borrador})
            with st.container(border=True):
                st.markdown(f"**Fecha:** {fecha_prog.strftime('%d-%m-%Y')} — **Turno:** {ot.TURNO_LABEL[turno_sel]}")
                st.markdown(f"**Camiones:** {', '.join(nombre_por_patente.get(p, p) for p in patentes_borrador)}")
                st.markdown(f"**Asignado a:** {asignados_nombres or '—'}")
                st.markdown(f"**Tipo de trabajo:** {tipo_resumen}")
                st.markdown("**Ítems:**")
                for categoria in ("inspeccion", "ticket", "item_key"):
                    del_categoria = [it for it in borrador if it["tipo_item"] == categoria]
                    if not del_categoria:
                        continue
                    st.markdown(f"*{etiqueta_categoria[categoria]}:*")
                    for it in del_categoria:
                        nombre_camion = nombre_por_patente.get(it["patente"], it["patente"])
                        st.markdown(f"- {it['descripcion']} — {nombre_camion} ({it['patente']})")

            col_aprobar, col_editar = st.columns(2)
            with col_aprobar:
                if st.button("✅ Aprobar y enviar", type="primary", key="ot_aprobar"):
                    resultado = ot.crear_y_enviar_ot(
                        engine, fecha_programada=fecha_prog, turno=turno_sel,
                        asignados_ids=asignados_ids, items=borrador, creado_por=usuario["nombre"],
                    )
                    mensaje = f"OT {resultado['numero_ot']} creada y enviada."
                    if resultado["emails_enviados"]:
                        mensaje += f" Email enviado a: {', '.join(resultado['emails_enviados'])}."
                    if resultado["emails_error"]:
                        flash(
                            "warning",
                            f"{mensaje} No se pudo enviar el email a: {'; '.join(resultado['emails_error'])}.",
                        )
                    else:
                        flash("success", mensaje)
                    del st.session_state["ot_borrador"]
                    st.session_state["ot_carrito"] = []
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
