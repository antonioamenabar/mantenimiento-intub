"""Programa de Mantenimiento - Intub

Referencia de cada cuánto corresponde cada trabajo de Mantenimiento
Programado -- horas, kilometraje y/o calendario, lo que ocurra primero.
No calcula vencimientos (eso lo hace el Dashboard); esto es la "letra
chica" de por qué el Dashboard dice lo que dice.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from src import auth, planificacion
from src.bootstrap import get_engine
from src.queries import opciones_patentes

st.set_page_config(page_title="Programa de Mantenimiento - Intub", layout="wide")

engine = get_engine()
usuario = auth.requerir_login(rol_requerido=auth.ROLES_GESTION)

st.markdown("<h1 style='text-align:center;'>🗓️ Programa de Mantenimiento</h1>", unsafe_allow_html=True)
st.caption(
    "Cada cuánto corresponde cada trabajo -- horas de uso, kilometraje y/o tiempo de "
    "calendario, lo que ocurra primero. 🟢 Confirmado con manual del fabricante · "
    "🟡 Estimado (práctica de industria) · 🔴 Sin dato de marca/intervalo todavía."
)

programa = planificacion.programa_mantenimiento(engine)
nombre_por_patente = dict(zip(opciones_patentes(engine)["patente"], opciones_patentes(engine)["nombre_corto"]))

if programa.empty:
    st.info("Todavía no hay reglas de mantención cargadas.")
    st.stop()

for categoria in ("camion", "equipo"):
    filas_cat = programa[programa["categoria"] == categoria]
    if filas_cat.empty:
        continue
    st.markdown(f"### {planificacion.CATEGORIA_LABEL[categoria]}")
    for nombre_item in filas_cat.sort_values("orden")["nombre"].unique():
        filas_item = filas_cat[filas_cat["nombre"] == nombre_item]
        with st.container(border=True):
            st.markdown(f"**{nombre_item}**")
            for _, regla in filas_item.iterrows():
                badge = planificacion.CONFIANZA_BADGE.get(regla["confianza"], "🔴")
                col_marca, col_intervalo = st.columns([1, 2])
                with col_marca:
                    st.markdown(f"{badge} {regla['marca_modelo']}")
                with col_intervalo:
                    st.markdown(regla["intervalo_texto"])
                if regla["es_generica"]:
                    st.caption("Aplica por defecto a los camiones sin componente específico registrado.")
                elif regla["camiones"]:
                    camiones_txt = ", ".join(
                        f"{nombre_por_patente.get(p, p)} ({p})" for p in regla["camiones"]
                    )
                    st.caption(f"Camiones con este componente: {camiones_txt}")
                if regla["fuente"]:
                    st.caption(f"Fuente: {regla['fuente']}")
                st.markdown("")

st.caption(
    "¿Falta un componente, o cambió un intervalo? Avísame y lo actualizo -- por ahora esta "
    "tabla se administra desde el código, no tiene edición propia en esta pantalla."
)
