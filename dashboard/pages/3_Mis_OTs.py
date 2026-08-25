"""Mis OTs - Intub

Un mecánico interno ve solo las OTs que le asignaron y las marca como
completadas. El Jefe ve todas (útil para cerrar a mano las de un taller
externo, que no tiene sesión propia, cuando avisa que terminó).

Pensada para completarse desde el celular o una tablet en terreno: layout
"centered" (más cómodo de leer angosto que "wide"), cada ítem de la OT en
su propio desplegable independiente (parte todo colapsado, se abre de a
uno), y los campos apilados en vertical en vez de en columnas -- así no se
achican al ancho de pantalla de un teléfono.
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


def _render_checklist_inspeccion(ot_item_id: int, subtipo: str) -> list[dict]:
    """El checklist completo de la ficha de `subtipo`, en vertical (foto,
    luego estado, luego observación si corresponde) -- pensado para
    completarse con el dedo en un celular, no lado a lado en columnas.
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
            archivo = st.file_uploader(
                "📷 Foto", type=["jpg", "jpeg", "png"], key=f"{prefijo}_foto",
            )
            estado = st.radio(
                "Estado", options=chk.ESTADOS_CHECKLIST, format_func=lambda e: chk.ESTADO_LABEL[e],
                key=f"{prefijo}_estado",
            )
            observacion = None
            if estado == "fuera_normal":
                observacion = st.text_input(
                    "¿Qué encontraste? (obligatorio)", key=f"{prefijo}_obs",
                    placeholder="Describe qué encontraste",
                )
        respuestas.append({
            "catalogo_id": int(fila_cat["id"]), "item": fila_cat["item"], "estado": estado,
            "observacion": observacion, "archivo": archivo,
        })
    return respuestas


def _render_falla(ot_item_id: int) -> dict:
    prefijo = f"falla_{ot_item_id}"
    sistema = st.selectbox("Sistema trabajado", options=chk.SISTEMAS_FALLA, key=f"{prefijo}_sistema")
    foto_antes = st.file_uploader("📷 Foto antes", type=["jpg", "jpeg", "png"], key=f"{prefijo}_antes")
    foto_despues = st.file_uploader("📷 Foto después", type=["jpg", "jpeg", "png"], key=f"{prefijo}_despues")
    return {"sistema": sistema, "foto_antes": foto_antes, "foto_despues": foto_despues, "horometro": None}


def _render_mantenimiento(ot_item_id: int) -> dict:
    prefijo = f"mant_{ot_item_id}"
    foto_antes = st.file_uploader("📷 Foto antes", type=["jpg", "jpeg", "png"], key=f"{prefijo}_antes")
    foto_despues = st.file_uploader("📷 Foto después", type=["jpg", "jpeg", "png"], key=f"{prefijo}_despues")
    horometro = None
    if st.checkbox("¿Se leyó horómetro?", key=f"{prefijo}_tiene_horas"):
        horometro = st.number_input("Horas", min_value=0, step=1, key=f"{prefijo}_horas")
    return {"sistema": None, "foto_antes": foto_antes, "foto_despues": foto_despues, "horometro": horometro}


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

            # Cada ítem de la OT (cada checklist de inspección, cada falla,
            # cada componente de mantenimiento, de cada camión) es su propio
            # desplegable, colapsado por defecto -- el mecánico los va
            # abriendo de a uno. El nombre del camión va en el título de
            # cada ítem porque una misma OT puede traer varios camiones.
            checklist_por_item = {}   # ot_item_id -> respuestas (solo inspección)
            falla_mant_por_item = {}  # ot_item_id -> {sistema, foto_antes, foto_despues, horometro}

            for _, it in items[items["tipo_item"] == "inspeccion"].iterrows():
                nombre_camion = nombre_por_patente.get(it["patente"], it["patente"])
                with st.expander(f"🔍 {it['referencia']} — {nombre_camion} ({it['patente']})", expanded=False):
                    checklist_por_item[it["id"]] = _render_checklist_inspeccion(it["id"], it["referencia"])

            for _, it in items[items["tipo_item"] == "ticket"].iterrows():
                nombre_camion = nombre_por_patente.get(it["patente"], it["patente"])
                with st.expander(f"⚠️ {it['descripcion'] or it['referencia']} — {nombre_camion} ({it['patente']})", expanded=False):
                    falla_mant_por_item[it["id"]] = _render_falla(it["id"])

            for _, it in items[items["tipo_item"] == "item_key"].iterrows():
                nombre_camion = nombre_por_patente.get(it["patente"], it["patente"])
                with st.expander(f"🛠️ {it['descripcion'] or it['referencia']} — {nombre_camion} ({it['patente']})", expanded=False):
                    falla_mant_por_item[it["id"]] = _render_mantenimiento(it["id"])

            notas = st.text_area("Notas de cierre (qué se hizo)", key=f"notas_{fila['id']}")

            if st.button("✅ Marcar como completada", type="primary", key=f"completar_{fila['id']}", width="stretch"):
                # Validación: cada ítem del checklist necesita foto, y si
                # quedó "Fuera de Normal" además necesita la observación.
                errores = []
                for _ot_item_id, respuestas in checklist_por_item.items():
                    for r in respuestas:
                        if r["archivo"] is None:
                            errores.append(f"Falta foto en «{r['item']}».")
                        if r["estado"] == "fuera_normal" and not (r["observacion"] or "").strip():
                            errores.append(f"«{r['item']}» quedó Fuera de Normal -- falta describir qué se encontró.")

                if errores:
                    st.warning("No se pudo guardar:\n\n" + "\n\n".join(f"- {e}" for e in errores))
                else:
                    for ot_item_id, respuestas in checklist_por_item.items():
                        chk.guardar_checklist_completo(engine, fila["id"], ot_item_id, respuestas)

                    horometros = {}
                    for ot_item_id, datos in falla_mant_por_item.items():
                        chk.guardar_sistema_y_fotos(
                            engine, fila["id"], ot_item_id,
                            datos["sistema"], datos["foto_antes"], datos["foto_despues"],
                        )
                        if datos["horometro"] is not None:
                            horometros[ot_item_id] = int(datos["horometro"])

                    ot.completar_ot(
                        engine, ot_id=fila["id"],
                        completado_por=usuario["nombre"], notas_cierre=notas, horometros=horometros,
                    )
                    flash("success", f"{fila['numero_ot']} marcada como completada.")
                    st.rerun()

with st.expander(f"Historial de completadas ({len(completadas)})"):
    if completadas.empty:
        st.info("Todavía no hay OTs completadas.")
    else:
        completadas_mostrar = completadas.copy()
        completadas_mostrar["tipo_trabajo"] = completadas_mostrar["tipo_trabajo"].map(ot.TIPO_TRABAJO_LABEL)
        st.dataframe(
            completadas_mostrar[[
                "numero_ot", "patentes", "tipo_trabajo", "completado_at", "completado_por", "notas_cierre",
            ]].rename(columns={
                "numero_ot": "OT", "patentes": "Camiones", "tipo_trabajo": "Tipo",
                "completado_at": "Completada", "completado_por": "Por", "notas_cierre": "Notas",
            }),
            hide_index=True, width="stretch",
        )
