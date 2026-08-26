"""Programa de Mantenimiento - Intub

Referencia de cada cuánto corresponde cada trabajo de Mantenimiento
Programado -- horas, kilometraje y/o calendario, lo que ocurra primero.
No calcula vencimientos (eso lo hace el Dashboard); esto es la "letra
chica" de por qué el Dashboard dice lo que dice.

El Supervisor/Admin puede definir reglas "por camión": elige directamente
las patentes a las que aplica (sin pasar por marca/modelo) y la duración
(horas y/o días calendario). Una regla así manda por sobre la genérica o
por marca que traiga el componente.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from src import auth, planificacion
from src.bootstrap import get_engine
from src.flash import flash, mostrar_flash
from src.queries import opciones_patentes

engine = get_engine()
usuario = auth.requerir_login(rol_requerido=auth.ROLES_OPERACION)

st.markdown("<h1 style='text-align:center;'>🗓️ Programa de Mantenimiento</h1>", unsafe_allow_html=True)
mostrar_flash()
st.caption(
    "Cada cuánto corresponde cada trabajo -- horas de uso, kilometraje y/o tiempo de "
    "calendario, lo que ocurra primero. 🟢 Confirmado con manual del fabricante · "
    "🟡 Estimado (práctica de industria) · 🔴 Sin dato de marca/intervalo todavía."
)

todas_patentes = opciones_patentes(engine)
nombre_por_patente = dict(zip(todas_patentes["patente"], todas_patentes["nombre_corto"]))

programa = planificacion.programa_mantenimiento(engine)
items_df = planificacion.catalogo_items(engine)

if items_df.empty:
    st.info("Todavía no hay catálogo de componentes cargado.")
    st.stop()

for categoria in ("camion", "equipo"):
    items_cat = items_df[items_df["categoria"] == categoria].sort_values("orden")
    if items_cat.empty:
        continue
    st.markdown(f"### {planificacion.CATEGORIA_LABEL[categoria]}")
    for _, item in items_cat.iterrows():
        filas_item = programa[programa["item_key"] == item["item_key"]] if not programa.empty else programa
        with st.container(border=True):
            st.markdown(f"**{item['nombre']}**")

            reglas_por_camion = filas_item[filas_item["es_por_camion"]] if not filas_item.empty else filas_item
            reglas_generales = filas_item[~filas_item["es_por_camion"]] if not filas_item.empty else filas_item

            if not reglas_por_camion.empty:
                st.caption("Reglas por camión (definidas a mano):")
                for _, regla in reglas_por_camion.iterrows():
                    camiones_txt = ", ".join(
                        f"{nombre_por_patente.get(p, p)} ({p})" for p in regla["camiones"]
                    )
                    col_info, col_borrar = st.columns([6, 1])
                    with col_info:
                        st.markdown(f"🔧 **{camiones_txt}** -- {regla['intervalo_texto']}")
                    with col_borrar:
                        if st.button("🗑️", key=f"regla_borrar_{regla['regla_id']}"):
                            planificacion.eliminar_regla(engine, int(regla["regla_id"]))
                            flash("success", "Regla eliminada.")
                            st.rerun()

            for _, regla in reglas_generales.iterrows():
                badge = planificacion.CONFIANZA_BADGE.get(regla["confianza"], "🔴")
                col_marca, col_intervalo = st.columns([1, 2])
                with col_marca:
                    st.markdown(f"{badge} {regla['marca_modelo']}")
                with col_intervalo:
                    st.markdown(regla["intervalo_texto"])
                if regla["es_generica"]:
                    st.caption("Aplica por defecto a los camiones sin componente específico registrado ni regla por camión.")
                elif regla["camiones"]:
                    camiones_txt = ", ".join(
                        f"{nombre_por_patente.get(p, p)} ({p})" for p in regla["camiones"]
                    )
                    st.caption(f"Camiones con este componente: {camiones_txt}")
                if regla["fuente"]:
                    st.caption(f"Fuente: {regla['fuente']}")
                st.markdown("")

            with st.popover("➕ Agregar regla por camión"):
                patentes_sel = st.multiselect(
                    "Camiones", options=todas_patentes["patente"].tolist(),
                    format_func=lambda p: f"{nombre_por_patente.get(p, p)} ({p})",
                    key=f"regla_patentes_{item['item_key']}",
                )
                col_horas, col_dias = st.columns(2)
                with col_horas:
                    horas_sel = st.number_input(
                        "Horas", min_value=0, step=10, value=0, key=f"regla_horas_{item['item_key']}",
                    )
                with col_dias:
                    dias_sel = st.number_input(
                        "Días calendario", min_value=0, step=10, value=0, key=f"regla_dias_{item['item_key']}",
                    )
                if st.button("Guardar regla", type="primary", key=f"regla_guardar_{item['item_key']}"):
                    if not patentes_sel:
                        st.warning("Elige al menos un camión.")
                    elif not horas_sel and not dias_sel:
                        st.warning("Define horas y/o días calendario -- al menos uno.")
                    else:
                        planificacion.guardar_regla_patentes(
                            engine, item_key=item["item_key"], patentes=patentes_sel,
                            intervalo_horas=int(horas_sel) or None, intervalo_dias=int(dias_sel) or None,
                            creado_por=usuario["nombre"],
                        )
                        flash("success", f"Regla guardada para {len(patentes_sel)} camión(es).")
                        st.rerun()
