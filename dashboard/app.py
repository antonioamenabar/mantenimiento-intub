"""Dashboard de Mantenimiento - Intub
4 cuadrantes: Inspecciones | Fallas | Mantenimiento Programado | Inventario

Uso:
    streamlit run dashboard/app.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from src import db, queries

st.set_page_config(page_title="Dashboard Mantenimiento - Intub", layout="wide")
st.title("🚛 Dashboard de Mantenimiento")

engine = db.get_engine()

col1, col2 = st.columns(2)
col3, col4 = st.columns(2)


def _icono(valor):
    if valor is None:
        return "—"
    return "✅" if valor else "❌"


def render_inspecciones():
    st.header("🔍 Inspecciones")
    st.caption("Semana actual — por cada día, si se hizo el checklist de Inicio y el de Fin de jornada (por separado).")

    diaria = queries.matriz_cumplimiento_diario(engine)
    semanal = queries.semanal_ultimas_semanas_cerradas(engine, n_semanas=2)

    if diaria.empty:
        st.info("No hay camiones cargados en la flota todavía.")
        return

    tabla = diaria.merge(semanal, on=["patente", "alias"], how="left")

    dias_cols = [f"{etiqueta} {momento}" for etiqueta in queries.DIAS_SEMANA for momento in ("Inicio", "Fin")]
    for col in dias_cols:
        tabla[col] = tabla[col].apply(_icono)
    tabla["Semanal (últ. 2 sem.)"] = tabla["inspeccion_semanal_2_sem"].apply(_icono)
    tabla = tabla.drop(columns=["inspeccion_semanal_2_sem"])

    tabla = tabla.rename(columns={"patente": "Patente", "alias": "Camión"})

    st.dataframe(tabla, use_container_width=True, hide_index=True)


with col1:
    render_inspecciones()

with col2:
    st.header("⚠️ Fallas")
    st.info("Próximamente. (Ya identificamos que se registran en el mismo "
            "formulario R-PR03-01, como 'Mantención Correctiva Base/Terreno'.)")

with col3:
    st.header("🛠️ Mantenimiento Programado")
    st.info("Próximamente.")

with col4:
    st.header("📦 Inventario")
    st.info("Próximamente.")
