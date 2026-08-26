"""Programa de Mantenimiento - Intub

Referencia de cada cuánto corresponde cada trabajo de Mantenimiento
Programado -- horas y/o días calendario, lo que ocurra primero. No
calcula vencimientos (eso lo hace el Dashboard); esto es la "letra
chica" de por qué el Dashboard dice lo que dice.

Vista en 3 niveles, cada uno con su propio desplegable (así se puede
tener todo comprimido y solo abrir lo que interesa):
  Camión / Equipo  →  cada ítem (Aceite motor, Bomba de agua, ...)  →
  una fila por camión de la flota, con el intervalo que le aplica hoy y
  un botón para editarlo puntualmente (sin pasar por marca/modelo).
Un botón "Comprimir todo" vuelve todo al primer nivel.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from src import auth, planificacion
from src.bootstrap import get_engine
from src.flash import flash, mostrar_flash

engine = get_engine()
usuario = auth.requerir_login(rol_requerido=auth.ROLES_OPERACION)

st.markdown("<h1 style='text-align:center;'>🗓️ Programa de Mantenimiento</h1>", unsafe_allow_html=True)
mostrar_flash()
st.caption(
    "Cada cuánto corresponde cada trabajo, por camión -- horas de uso y/o tiempo de "
    "calendario, lo que ocurra primero. 🟢 Confirmado · 🟡 Estimado · 🔴 Sin dato."
)

items_df = planificacion.catalogo_items(engine)
if items_df.empty:
    st.info("Todavía no hay catálogo de componentes cargado.")
    st.stop()


def _key_categoria(categoria: str) -> str:
    return f"prog_cat_{categoria}"


def _key_item(item_key: str) -> str:
    return f"prog_item_{item_key}"


if st.button("🗂️ Comprimir todo", key="prog_comprimir_todo"):
    for categoria in planificacion.CATEGORIA_LABEL:
        st.session_state[_key_categoria(categoria)] = False
    for _, item in items_df.iterrows():
        st.session_state[_key_item(item["item_key"])] = False
    st.rerun()

for categoria in ("camion", "equipo"):
    items_cat = items_df[items_df["categoria"] == categoria].sort_values("orden")
    if items_cat.empty:
        continue

    with st.expander(planificacion.CATEGORIA_LABEL[categoria], expanded=False, key=_key_categoria(categoria)):
        for _, item in items_cat.iterrows():
            item_key = item["item_key"]
            with st.expander(item["nombre"], expanded=False, key=_key_item(item_key)):
                tabla = planificacion.tabla_item_por_patente(engine, item_key)

                for _, fila in tabla.iterrows():
                    badge = planificacion.CONFIANZA_BADGE.get(fila["confianza"], "🔴")
                    marca_especifica = " 🔧" if fila["es_especifica"] else ""
                    col_patente, col_intervalo, col_editar = st.columns([2, 4, 1], vertical_alignment="center")
                    with col_patente:
                        st.markdown(f"**{fila['nombre_corto']}** ({fila['patente']}){marca_especifica}")
                    with col_intervalo:
                        st.markdown(f"{badge} {fila['intervalo_texto']}")
                    with col_editar:
                        with st.popover("✏️", key=f"prog_editar_{item_key}_{fila['patente']}"):
                            st.caption(f"{fila['nombre_corto']} ({fila['patente']}) -- {item['nombre']}")
                            col_horas, col_dias = st.columns(2)
                            with col_horas:
                                horas_edit = st.number_input(
                                    "Horas", min_value=0, step=10,
                                    value=int(fila["intervalo_horas"]) if fila["es_especifica"] and fila["intervalo_horas"] else 0,
                                    key=f"prog_horas_{item_key}_{fila['patente']}",
                                )
                            with col_dias:
                                dias_edit = st.number_input(
                                    "Días calendario", min_value=0, step=10,
                                    value=int(fila["intervalo_dias"]) if fila["es_especifica"] and fila["intervalo_dias"] else 0,
                                    key=f"prog_dias_{item_key}_{fila['patente']}",
                                )
                            if st.button("Guardar", type="primary", key=f"prog_guardar_{item_key}_{fila['patente']}", width="stretch"):
                                if not horas_edit and not dias_edit:
                                    st.warning("Define horas y/o días calendario -- al menos uno.")
                                else:
                                    planificacion.actualizar_regla_patente(
                                        engine, item_key=item_key, patente=fila["patente"],
                                        regla_id_anterior=fila["regla_id"],
                                        intervalo_horas=int(horas_edit) or None, intervalo_dias=int(dias_edit) or None,
                                        creado_por=usuario["nombre"],
                                    )
                                    flash("success", f"Regla de {fila['nombre_corto']} actualizada.")
                                    st.rerun()
                            if fila["es_especifica"]:
                                if st.button(
                                    "↩️ Quitar (volver a la regla general)",
                                    key=f"prog_quitar_{item_key}_{fila['patente']}", width="stretch",
                                ):
                                    planificacion.eliminar_regla(engine, int(fila["regla_id"]))
                                    flash("success", f"{fila['nombre_corto']} vuelve a la regla general.")
                                    st.rerun()

                st.caption("🔧 = regla puntual para ese camión (distinta de la general del componente).")
