"""Mis OTs - Intub

Un mecánico interno ve solo las OTs que le asignaron y las marca como
completadas. El Jefe ve todas (útil para cerrar a mano las de un taller
externo, que no tiene sesión propia, cuando avisa que terminó).

Pensada para completarse desde el celular o una tablet en terreno: layout
"centered" (más cómodo de leer angosto que "wide"), cada ítem de la OT en
su propio desplegable independiente (parte todo colapsado, se abre de a
uno), y los campos apilados en vertical en vez de en columnas -- así no se
achican al ancho de pantalla de un teléfono.

Cada ítem (cada Inspección, Falla o Mantenimiento Programado) se puede
"Finalizar" por separado -- no hace falta terminar toda la OT de una vez.
Un ítem ya finalizado desaparece de la lista de pendientes. La OT completa
se cierra aparte, con un botón propio; si queda algún ítem sin finalizar,
pide obligatoriamente decir por qué antes de dejar cerrar.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from src import auth, ordenes_trabajo as ot, ot_checklist as chk
from src.bootstrap import get_engine
from src.flash import flash, mostrar_flash
from src.queries import opciones_patentes

st.set_page_config(page_title="Mis OTs - Intub", layout="centered")

engine = get_engine()
usuario = auth.requerir_login()

st.markdown("<h1 style='text-align:center;'>📝 Mis OTs</h1>", unsafe_allow_html=True)
mostrar_flash()

if usuario["rol"] == "mecanico":
    tabla = ot.ots_de_usuario(engine, usuario["id"])
    st.caption("OTs asignadas a ti.")
else:
    tabla = ot.ots_todas(engine)
    st.caption("Todas las OTs -- útil para cerrar a mano las de un taller externo cuando avisa que terminó.")

if tabla.empty:
    st.info("No hay OTs para mostrar.")
    st.stop()

nombre_por_patente = dict(zip(opciones_patentes(engine)["patente"], opciones_patentes(engine)["nombre_corto"]))

pendientes = tabla[tabla["estado"] == "enviada"]
completadas = tabla[tabla["estado"] == "completada"]


def _render_checklist_inspeccion(ot_item_id: int, subtipo: str) -> tuple[list[dict], str]:
    """El checklist completo de la ficha de `subtipo`, en vertical (foto,
    luego estado, luego observación si corresponde) -- pensado para
    completarse con el dedo en un celular, no lado a lado en columnas.
    Devuelve (respuestas, comentario general de toda la ficha).
    """
    catalogo = chk.catalogo_para_subtipo(engine, subtipo)
    respuestas = []
    grupo_anterior = None
    for _, fila_cat in catalogo.iterrows():
        if fila_cat["grupo"] != grupo_anterior:
            st.markdown(f"**{fila_cat['grupo']}**")
            grupo_anterior = fila_cat["grupo"]
        prefijo = f"chk_{ot_item_id}_{fila_cat['id']}"
        with st.container(border=True):
            st.markdown(f"**{fila_cat['item']}**")
            archivos = st.file_uploader(
                "📷 Foto(s)", type=["jpg", "jpeg", "png"], key=f"{prefijo}_foto",
                accept_multiple_files=True,
            )
            valor = None
            if fila_cat["item"] in chk.ITEMS_CON_VALOR:
                valor = st.text_input(
                    f"Lectura de {fila_cat['item'].lower()}", key=f"{prefijo}_valor",
                )
            estado = st.radio(
                "Estado", options=chk.ESTADOS_CHECKLIST, format_func=lambda e: chk.ESTADO_LABEL[e],
                key=f"{prefijo}_estado",
            )
            observacion = None
            if estado in chk.ESTADOS_CON_OBSERVACION_OBLIGATORIA:
                placeholder = (
                    "Describe qué encontraste" if estado == "fuera_normal"
                    else "Describe por qué no aplica en este camión"
                )
                observacion = st.text_input(
                    "Observación (obligatoria)", key=f"{prefijo}_obs", placeholder=placeholder,
                )
        respuestas.append({
            "catalogo_id": int(fila_cat["id"]), "item": fila_cat["item"], "estado": estado,
            "observacion": observacion, "valor": valor, "archivos": archivos,
        })
    comentario = st.text_area("Comentario (opcional)", key=f"chk_{ot_item_id}_comentario")
    return respuestas, comentario


def _render_falla(ot_item_id: int) -> dict:
    prefijo = f"falla_{ot_item_id}"
    sistema = st.selectbox("Sistema trabajado", options=chk.SISTEMAS_FALLA, key=f"{prefijo}_sistema")
    foto_antes = st.file_uploader("📷 Foto antes", type=["jpg", "jpeg", "png"], key=f"{prefijo}_antes")
    foto_despues = st.file_uploader("📷 Foto después", type=["jpg", "jpeg", "png"], key=f"{prefijo}_despues")
    comentario = st.text_area("Comentario (opcional)", key=f"{prefijo}_comentario")
    return {
        "sistema": sistema, "foto_antes": foto_antes, "foto_despues": foto_despues,
        "horometro": None, "comentario": comentario,
    }


def _render_mantenimiento(ot_item_id: int) -> dict:
    prefijo = f"mant_{ot_item_id}"
    foto_antes = st.file_uploader("📷 Foto antes", type=["jpg", "jpeg", "png"], key=f"{prefijo}_antes")
    foto_despues = st.file_uploader("📷 Foto después", type=["jpg", "jpeg", "png"], key=f"{prefijo}_despues")
    horometro = None
    if st.checkbox("¿Se leyó horómetro?", key=f"{prefijo}_tiene_horas"):
        horometro = st.number_input("Horas", min_value=0, step=1, key=f"{prefijo}_horas")
    comentario = st.text_area("Comentario (opcional)", key=f"{prefijo}_comentario")
    return {
        "sistema": None, "foto_antes": foto_antes, "foto_despues": foto_despues,
        "horometro": horometro, "comentario": comentario,
    }


def _errores_checklist(respuestas: list[dict]) -> list[str]:
    errores = []
    for r in respuestas:
        if not r["archivos"]:
            errores.append(f"Falta foto en «{r['item']}».")
        if r["estado"] in chk.ESTADOS_CON_OBSERVACION_OBLIGATORIA and not (r["observacion"] or "").strip():
            errores.append(f"«{r['item']}» quedó {chk.ESTADO_LABEL[r['estado']]} -- falta la observación.")
    return errores


st.markdown(f"#### Pendientes ({len(pendientes)})")
if pendientes.empty:
    st.info("No hay OTs pendientes.")
else:
    for _, fila in pendientes.iterrows():
        fecha_prog = fila.get("fecha_programada") or "—"
        turno_txt = ot.TURNO_LABEL.get(fila.get("turno"), fila.get("turno") or "—")
        titulo_ot = (
            f"{fila['numero_ot']} — {fecha_prog} ({turno_txt}) — {fila.get('patentes', '—')} — "
            f"{ot.TIPO_TRABAJO_LABEL.get(fila['tipo_trabajo'], fila['tipo_trabajo'])}"
        )
        with st.expander(titulo_ot, expanded=False):
            items = ot.items_de_ot(engine, fila["id"])
            items_pendientes = items[items["estado"] != "completada"]
            n_completados = len(items) - len(items_pendientes)
            st.caption(f"✅ {n_completados} de {len(items)} tareas finalizadas")

            # Cada ítem pendiente (cada checklist de inspección, cada
            # falla, cada componente de mantenimiento, de cada camión) es
            # su propio desplegable, colapsado por defecto, con su propio
            # botón "Finalizar tarea" -- una vez finalizado desaparece de
            # esta lista. El nombre del camión va en el título de cada
            # ítem porque una misma OT puede traer varios camiones.
            for _, it in items_pendientes[items_pendientes["tipo_item"] == "inspeccion"].iterrows():
                nombre_camion = nombre_por_patente.get(it["patente"], it["patente"])
                with st.expander(f"🔍 {it['referencia']} — {nombre_camion} ({it['patente']})", expanded=False):
                    respuestas, comentario_insp = _render_checklist_inspeccion(it["id"], it["referencia"])
                    if st.button("✅ Finalizar tarea", key=f"fin_{it['id']}", width="stretch"):
                        errores = _errores_checklist(respuestas)
                        if errores:
                            st.warning("No se pudo guardar:\n\n" + "\n\n".join(f"- {e}" for e in errores))
                        else:
                            chk.guardar_checklist_completo(engine, fila["id"], int(it["id"]), respuestas)
                            ot.completar_item(
                                engine, ot_item_id=int(it["id"]), completado_por=usuario["nombre"],
                                comentario=comentario_insp,
                            )
                            flash("success", f"«{it['referencia']} — {nombre_camion}» finalizada.")
                            st.rerun()

            for _, it in items_pendientes[items_pendientes["tipo_item"] == "ticket"].iterrows():
                nombre_camion = nombre_por_patente.get(it["patente"], it["patente"])
                with st.expander(f"⚠️ {it['descripcion'] or it['referencia']} — {nombre_camion} ({it['patente']})", expanded=False):
                    datos = _render_falla(it["id"])
                    if st.button("✅ Finalizar tarea", key=f"fin_{it['id']}", width="stretch"):
                        chk.guardar_sistema_y_fotos(
                            engine, fila["id"], int(it["id"]),
                            datos["sistema"], datos["foto_antes"], datos["foto_despues"],
                        )
                        ot.completar_item(
                            engine, ot_item_id=int(it["id"]), completado_por=usuario["nombre"],
                            comentario=datos["comentario"],
                        )
                        flash("success", f"«{it['descripcion'] or it['referencia']} — {nombre_camion}» finalizada.")
                        st.rerun()

            for _, it in items_pendientes[items_pendientes["tipo_item"] == "item_key"].iterrows():
                nombre_camion = nombre_por_patente.get(it["patente"], it["patente"])
                with st.expander(f"🛠️ {it['descripcion'] or it['referencia']} — {nombre_camion} ({it['patente']})", expanded=False):
                    datos = _render_mantenimiento(it["id"])
                    if st.button("✅ Finalizar tarea", key=f"fin_{it['id']}", width="stretch"):
                        chk.guardar_sistema_y_fotos(
                            engine, fila["id"], int(it["id"]),
                            None, datos["foto_antes"], datos["foto_despues"],
                        )
                        horometro = int(datos["horometro"]) if datos["horometro"] is not None else None
                        ot.completar_item(
                            engine, ot_item_id=int(it["id"]), completado_por=usuario["nombre"],
                            horometro=horometro, comentario=datos["comentario"],
                        )
                        flash("success", f"«{it['descripcion'] or it['referencia']} — {nombre_camion}» finalizada.")
                        st.rerun()

            if items_pendientes.empty:
                st.success("Todas las tareas de esta OT están finalizadas -- ya se puede cerrar.")

            st.divider()
            notas = st.text_area("Notas de cierre (opcional)", key=f"notas_{fila['id']}")
            notas_pend = ""
            if not items_pendientes.empty:
                notas_pend = st.text_area(
                    "¿Por qué quedan tareas pendientes? (obligatorio para cerrar así)",
                    key=f"notas_pend_{fila['id']}",
                    placeholder="Ej: falta repuesto, se reprograma para la próxima semana...",
                )

            if st.button("🔒 Cerrar OT", type="primary", key=f"cerrar_{fila['id']}", width="stretch"):
                if not items_pendientes.empty and not notas_pend.strip():
                    st.warning("Quedan tareas pendientes -- cuenta por qué antes de cerrar la OT.")
                else:
                    ot.completar_ot(
                        engine, ot_id=fila["id"], completado_por=usuario["nombre"],
                        notas_cierre=notas, notas_pendientes=notas_pend,
                    )
                    flash("success", f"{fila['numero_ot']} cerrada.")
                    st.rerun()

with st.expander(f"Historial de completadas ({len(completadas)})"):
    if completadas.empty:
        st.info("Todavía no hay OTs completadas.")
    else:
        completadas_mostrar = completadas.copy()
        completadas_mostrar["tipo_trabajo"] = completadas_mostrar["tipo_trabajo"].map(ot.TIPO_TRABAJO_LABEL)
        completadas_mostrar["notas_pendientes"] = completadas_mostrar["notas_pendientes"].fillna("—")
        st.dataframe(
            completadas_mostrar[[
                "numero_ot", "patentes", "asignados_nombres", "tipo_trabajo", "completado_at", "completado_por",
                "notas_cierre", "notas_pendientes",
            ]].rename(columns={
                "numero_ot": "OT", "patentes": "Camiones", "asignados_nombres": "Asignado a", "tipo_trabajo": "Tipo",
                "completado_at": "Completada", "completado_por": "Por", "notas_cierre": "Notas",
                "notas_pendientes": "Tareas sin finalizar",
            }),
            hide_index=True, width="stretch",
        )
