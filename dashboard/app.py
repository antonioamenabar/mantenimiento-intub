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


def render_inspecciones():
    st.header("🔍 Inspecciones")

    st.subheader("Cumplimiento diario (hoy)")
    diario = queries.cumplimiento_diario(engine)
    if diario.empty:
        st.info("No hay camiones cargados en la flota todavía.")
    else:
        total = len(diario)
        completos = diario["completo"].sum()
        st.metric("Camiones con inspección completa hoy", f"{completos}/{total}")
        st.dataframe(
            diario.rename(columns={
                "patente": "Patente", "alias": "Camión",
                "inspeccion_inicio": "Inicio jornada", "inspeccion_fin": "Fin jornada",
                "completo": "Completo",
            }),
            use_container_width=True, hide_index=True,
        )

    st.subheader("Cumplimiento semanal (inspección detallada)")
    semanal = queries.cumplimiento_semanal(engine)
    if semanal.empty:
        st.info("No hay camiones cargados en la flota todavía.")
    else:
        conteo = semanal["estado"].value_counts()
        c1, c2, c3 = st.columns(3)
        c1.metric("✅ Hechas", int(conteo.get("hecha", 0)))
        c2.metric("⏳ Pendientes", int(conteo.get("pendiente", 0)))
        c3.metric("🔴 Vencidas", int(conteo.get("vencida", 0)))
        st.dataframe(
            semanal.rename(columns={"patente": "Patente", "alias": "Camión", "estado": "Estado"}),
            use_container_width=True, hide_index=True,
        )


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
