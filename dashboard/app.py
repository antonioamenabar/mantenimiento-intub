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


def _icono(valor):
    if valor is None:
        return "—"
    if valor == "N/A":
        return "N/A"
    return "✅" if valor else "❌"


def _tabla_html(tabla) -> str:
    """Tabla HTML propia: header combinado (día arriba, Inicio/Fin abajo,
    como celda unida) y todo centrado. El widget nativo de Streamlit no
    permite ni lo uno ni lo otro.
    """
    dias = queries.DIAS_SEMANA
    head_dias = "".join(f'<th colspan="2">{d}</th>' for d in dias)
    head_sub = "".join("<th>Inicio</th><th>Fin</th>" for _ in dias)

    filas_html = []
    for _, row in tabla.iterrows():
        celdas_dias = "".join(
            f"<td>{_icono(row[f'{d} {momento}'])}</td>"
            for d in dias for momento in ("Inicio", "Fin")
        )
        filas_html.append(
            "<tr>"
            f"<td class='nombre'>{row['nombre_corto']}</td>"
            f"<td class='patente'>{row['patente']}</td>"
            f"{celdas_dias}"
            f"<td>{_icono(row['inspeccion_semanal_2_sem'])}</td>"
            "</tr>"
        )

    return f"""
    <style>
      .tabla-inspecciones {{
        border-collapse: collapse; font-size: 13px; width: 100%;
      }}
      .tabla-inspecciones th, .tabla-inspecciones td {{
        border: 1px solid rgba(128,128,128,0.35);
        padding: 4px 8px;
        text-align: center;
        white-space: nowrap;
      }}
      .tabla-inspecciones td.nombre, .tabla-inspecciones td.patente {{
        text-align: left; font-weight: 500;
      }}
      .tabla-inspecciones td.patente {{ opacity: 0.7; font-size: 12px; }}
      .tabla-inspecciones thead th {{
        background: rgba(128,128,128,0.12);
      }}
    </style>
    <table class="tabla-inspecciones">
      <thead>
        <tr>
          <th rowspan="2">Camión</th>
          <th rowspan="2">Patente</th>
          {head_dias}
          <th rowspan="2">Semanal<br>(últ. 2 sem.)</th>
        </tr>
        <tr>{head_sub}</tr>
      </thead>
      <tbody>
        {"".join(filas_html)}
      </tbody>
    </table>
    """


def render_inspecciones():
    st.header("🔍 Inspecciones")
    st.caption("Por cada día, si se hizo el checklist de Inicio y el de Fin de jornada (por separado).")

    opciones = queries.opciones_semana()
    idx = st.selectbox(
        "Semana", options=range(len(opciones)), format_func=lambda i: opciones[i][1], key="semana_inspecciones",
    )
    semana_inicio = opciones[idx][0]

    diaria = queries.matriz_cumplimiento_diario(engine, semana_inicio=semana_inicio)
    semanal = queries.semanal_ultimas_semanas_cerradas(engine, n_semanas=2, semana_referencia=semana_inicio)

    if diaria.empty:
        st.info("No hay camiones cargados en la flota todavía.")
        return

    tabla = diaria.merge(semanal, on="patente", how="left")
    st.html(_tabla_html(tabla))


render_inspecciones()

st.divider()
col2, col3, col4 = st.columns(3)

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
