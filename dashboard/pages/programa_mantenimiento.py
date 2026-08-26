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

import pandas as pd
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

# Una sola pasada de consultas para TODOS los ítems -- `st.expander` en
# Streamlit ejecuta su contenido aunque esté colapsado (no es "carga
# perezosa"), así que si cada ítem consultara la base por su cuenta acá
# adentro, la página haría ~4 consultas x 14 ítems = 56 viajes a la base
# en cada carga. `todos_items_por_patente` carga las tablas base una vez
# y arma cada tabla en memoria.
# Además queda en caché (`st.cache_data`): CUALQUIER clic en esta página
# (abrir un desplegable, "Comprimir todo", etc.) hace que Streamlit
# rehaga todo el script -- sin caché, volvería a pedir la base entera
# incluso para algo tan simple como cerrar un acordeón. `_engine` con
# guion bajo: así Streamlit no intenta "hashearlo" para la clave de
# caché (no se puede, ni tiene sentido -- es la misma conexión siempre).
# Se limpia a mano (`.clear()`) apenas se guarda/quita una regla, para
# que el cambio se vea de inmediato sin esperar los 60 segundos del TTL.
@st.cache_data(ttl=60, show_spinner=False)
def _cargar_tablas_por_item(_engine):
    return planificacion.todos_items_por_patente(_engine)


tablas_por_item = _cargar_tablas_por_item(engine)

# "Comprimir todo": en vez de sobrescribir el estado de cada `st.expander`
# uno por uno (con `key` fijo, no siempre sincroniza al toque), se cambia
# la clave de TODOS los expanders a una nueva que nunca existió -- así
# vuelven solos a su valor por defecto (`expanded=False`), sin ambigüedad.
if "prog_reset_gen" not in st.session_state:
    st.session_state["prog_reset_gen"] = 0
_gen = st.session_state["prog_reset_gen"]


def _key_categoria(categoria: str) -> str:
    return f"prog_cat_{categoria}_{_gen}"


def _key_item(item_key: str) -> str:
    return f"prog_item_{item_key}_{_gen}"


if st.button("🗂️ Comprimir todo", key="prog_comprimir_todo"):
    st.session_state["prog_reset_gen"] += 1
    st.rerun()

for categoria in ("camion", "equipo"):
    items_cat = items_df[items_df["categoria"] == categoria].sort_values("orden")
    if items_cat.empty:
        continue

    with st.expander(planificacion.CATEGORIA_LABEL[categoria], expanded=False, key=_key_categoria(categoria)):
        for _, item in items_cat.iterrows():
            item_key = item["item_key"]
            with st.expander(item["nombre"], expanded=False, key=_key_item(item_key)):
                tabla = tablas_por_item[item_key]

                with st.popover("✏️ Editar varios camiones a la vez", key=f"prog_masivo_{item_key}"):
                    st.caption(
                        f"Aplica la misma regla a los camiones que elijas -- {item['nombre']}. "
                        "Útil cuando toda la flota (o varios) comparte el mismo intervalo."
                    )
                    etiqueta_patente = dict(zip(
                        tabla["patente"],
                        tabla["nombre_corto"] + " (" + tabla["patente"] + ") -- " + tabla["intervalo_texto"],
                    ))
                    patentes_masivo = st.multiselect(
                        "Camiones", options=tabla["patente"].tolist(),
                        format_func=lambda p: etiqueta_patente.get(p, p),
                        key=f"prog_masivo_patentes_{item_key}",
                    )
                    col_h_masivo, col_d_masivo = st.columns(2)
                    with col_h_masivo:
                        horas_masivo = st.number_input(
                            "Horas", min_value=0, step=10, value=0, key=f"prog_masivo_horas_{item_key}",
                        )
                    with col_d_masivo:
                        dias_masivo = st.number_input(
                            "Días calendario", min_value=0, step=10, value=0, key=f"prog_masivo_dias_{item_key}",
                        )
                    if st.button(
                        "Aplicar a los seleccionados", type="primary",
                        key=f"prog_masivo_guardar_{item_key}", width="stretch",
                    ):
                        if not patentes_masivo:
                            st.warning("Elige al menos un camión.")
                        elif not horas_masivo and not dias_masivo:
                            st.warning("Define horas y/o días calendario -- al menos uno.")
                        else:
                            planificacion.actualizar_regla_patentes_masivo(
                                engine, item_key=item_key, patentes=patentes_masivo,
                                intervalo_horas=int(horas_masivo) or None, intervalo_dias=int(dias_masivo) or None,
                                creado_por=usuario["nombre"],
                            )
                            _cargar_tablas_por_item.clear()
                            flash("success", f"Regla aplicada a {len(patentes_masivo)} camión(es).")
                            st.rerun()

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
                            # pd.notna(): si la regla puntual solo definió horas (o
                            # solo días), el otro campo llega NULL -- y por cómo pandas
                            # mezcla NULL con números reales en la misma columna, puede
                            # llegar como NaN en vez de None; un `if valor:` a secas no
                            # lo filtra (NaN es "verdadero"), e int(nan) revienta.
                            horas_val = fila["intervalo_horas"]
                            dias_val = fila["intervalo_dias"]
                            with col_horas:
                                horas_edit = st.number_input(
                                    "Horas", min_value=0, step=10,
                                    value=int(horas_val) if fila["es_especifica"] and pd.notna(horas_val) and horas_val else 0,
                                    key=f"prog_horas_{item_key}_{fila['patente']}",
                                )
                            with col_dias:
                                dias_edit = st.number_input(
                                    "Días calendario", min_value=0, step=10,
                                    value=int(dias_val) if fila["es_especifica"] and pd.notna(dias_val) and dias_val else 0,
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
                                    _cargar_tablas_por_item.clear()
                                    flash("success", f"Regla de {fila['nombre_corto']} actualizada.")
                                    st.rerun()
                            if fila["es_especifica"]:
                                if st.button(
                                    "↩️ Quitar (volver a la regla general)",
                                    key=f"prog_quitar_{item_key}_{fila['patente']}", width="stretch",
                                ):
                                    planificacion.quitar_patente_de_regla(engine, int(fila["regla_id"]), fila["patente"])
                                    _cargar_tablas_por_item.clear()
                                    flash("success", f"{fila['nombre_corto']} vuelve a la regla general.")
                                    st.rerun()

                st.caption("🔧 = regla puntual para ese camión (distinta de la general del componente).")
