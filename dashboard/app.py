"""Dashboard de Mantenimiento - Intub
4 cuadrantes: Inspecciones | Fallas | Mantenimiento Programado | Inventario

Uso:
    streamlit run dashboard/app.py
"""
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from src import db, queries

st.set_page_config(page_title="Dashboard Mantenimiento - Intub", layout="wide")

st.markdown(
    """
    <style>
      .block-container { padding-top: 1rem !important; }
    </style>
    <h1 style='text-align:center; margin-top:0;'>🚛 Dashboard de Mantenimiento</h1>
    """,
    unsafe_allow_html=True,
)

engine = db.get_engine()

# Ancho objetivo de la tabla de Inspecciones (~1/2 de una pantalla de
# escritorio típica). Los filtros de arriba se fuerzan al mismo ancho (o la
# mitad, para el de semana) para que quede todo alineado.
TABLE_WIDTH_PX = 620
TABLE_FONT_PX = 12
# Ancho de la tabla de Fallas, pensado para quedar al lado de Inspecciones
# (no debajo), con columnas al mínimo para que quepa todo sin scroll.
FALLAS_WIDTH_PX = 400


def _icono(valor):
    if valor is None:
        return "—"
    if valor in ("N/A", "?"):
        return valor
    return "✅" if valor else "❌"


def _celda(valor, foto_url):
    icono = _icono(valor)
    if valor in (True, "?") and foto_url:
        return f'<a href="{foto_url}" target="_blank" title="Ver foto del reporte">{icono}</a>'
    return icono


def _tabla_html(tabla, semana_inicio) -> str:
    """Tabla HTML propia: header combinado (día arriba, con su número de
    día del mes -- ej. "Lun 17" -- e Inicio/Fin abajo, como celda unida),
    todo centrado, y las ✅ con foto son un link directo al reporte de
    Datascope. El widget nativo de Streamlit no permite nada de esto.
    """
    dias = queries.DIAS_SEMANA
    etiquetas_dias = [
        f"{etiqueta} {(semana_inicio + timedelta(days=i)).day}"
        for i, etiqueta in enumerate(dias)
    ]
    head_dias = "".join(f'<th colspan="2">{d}</th>' for d in etiquetas_dias)
    head_sub = "".join("<th>I</th><th>F</th>" for _ in dias)

    filas_html = []
    for _, row in tabla.iterrows():
        celdas_dias = "".join(
            f"<td class='dia'>{_celda(row[f'{d} {momento}'], row.get(f'{d} {momento}_foto'))}</td>"
            for d in dias for momento in ("Inicio", "Fin")
        )
        pct = row["pct_cumplimiento"]
        # pandas guarda los None de una columna float como NaN; NaN != NaN
        # es la forma más simple de detectarlo sin depender de pandas aquí.
        pct_txt = f"{pct:.0f}%" if pct is not None and pct == pct else "—"
        filas_html.append(
            "<tr>"
            f"<td class='patente'>{row['patente']}</td>"
            f"<td class='nombre'>{row['nombre_corto']}</td>"
            f"{celdas_dias}"
            f"<td class='dia'>{_icono(row['inspeccion_semanal_2_sem'])}</td>"
            f"<td class='dia pct'>{pct_txt}</td>"
            "</tr>"
        )

    return f"""
    <style>
      .tabla-inspecciones {{
        border-collapse: collapse; font-size: 12px; width: {TABLE_WIDTH_PX}px;
      }}
      .tabla-inspecciones th, .tabla-inspecciones td {{
        border: 1px solid rgba(128,128,128,0.35);
        padding: 2px 4px;
        text-align: center;
        white-space: nowrap;
        line-height: 1.2;
        box-sizing: border-box;
      }}
      .tabla-inspecciones td.dia {{ width: 36px; }}
      .tabla-inspecciones td.pct {{ font-weight: 600; }}
      .tabla-inspecciones td.nombre, .tabla-inspecciones td.patente {{
        text-align: left; font-weight: 500;
      }}
      .tabla-inspecciones td.patente {{ opacity: 0.7; font-size: 11px; width: 62px; }}
      .tabla-inspecciones td.nombre {{ width: 88px; }}
      .tabla-inspecciones a {{ text-decoration: none; }}
      .tabla-inspecciones thead th {{
        background: rgba(128,128,128,0.12); font-size: 10px;
      }}
    </style>
    <table class="tabla-inspecciones">
      <thead>
        <tr>
          <th rowspan="2">Patente</th>
          <th rowspan="2">Camión</th>
          {head_dias}
          <th rowspan="2">Sem.<br>2 sem.</th>
          <th rowspan="2">%<br>Cumpl.</th>
        </tr>
        <tr>{head_sub}</tr>
      </thead>
      <tbody>
        {"".join(filas_html)}
      </tbody>
    </table>
    """


def _tabla_fallas_html(tabla) -> str:
    """Tabla HTML propia para Fallas: Patente, Camión, Crítica/Alta/Media/Baja,
    antigüedad (3 rangos) y Total, con las columnas de prioridad coloreadas
    por severidad. Columnas al mínimo para que quepa al lado de Inspecciones.
    """
    color = {"Crítica": "#d32f2f", "Alta": "#f57c00", "Media": "#fbc02d", "Baja": "#388e3c"}
    cols_prioridad = list(queries.PRIORIDAD_LABEL.values())
    cols_antiguedad = queries.ANTIGUEDAD_BUCKETS
    head_antiguedad_corto = {
        "Menos de 7 días": "<7 días",
        "Entre 8 y 20 días": "8-20 días",
        "Más de 20 días": ">20 días",
    }

    filas_html = []
    for _, row in tabla.iterrows():
        celdas_prio = "".join(f"<td class='num'>{row[c]}</td>" for c in cols_prioridad)
        celdas_edad = "".join(f"<td class='num'>{row[c]}</td>" for c in cols_antiguedad)
        filas_html.append(
            "<tr>"
            f"<td class='patente'>{row['patente']}</td>"
            f"<td class='nombre'>{row['nombre_corto']}</td>"
            f"{celdas_prio}"
            f"{celdas_edad}"
            f"<td class='num total'>{row['Total']}</td>"
            "</tr>"
        )

    head_prioridad = "".join(f"<th style='color:{color[c]}'>{c}</th>" for c in cols_prioridad)
    head_antiguedad = "".join(f"<th>{head_antiguedad_corto[c]}</th>" for c in cols_antiguedad)

    return f"""
    <style>
      .tabla-fallas {{
        border-collapse: collapse; font-size: 11px; width: {FALLAS_WIDTH_PX}px;
      }}
      .tabla-fallas th, .tabla-fallas td {{
        border: 1px solid rgba(128,128,128,0.35);
        padding: 2px 3px;
        text-align: center;
        white-space: nowrap;
        box-sizing: border-box;
      }}
      .tabla-fallas td.num {{ width: 26px; }}
      .tabla-fallas td.total {{ font-weight: 600; }}
      .tabla-fallas td.nombre, .tabla-fallas td.patente {{ text-align: left; font-weight: 500; }}
      .tabla-fallas td.patente {{ opacity: 0.7; font-size: 10px; width: 46px; }}
      .tabla-fallas td.nombre {{ width: 62px; }}
      .tabla-fallas thead th {{ background: rgba(128,128,128,0.12); font-size: 9px; font-weight: 700; }}
    </style>
    <table class="tabla-fallas">
      <thead>
        <tr>
          <th>Patente</th>
          <th>Camión</th>
          {head_prioridad}
          {head_antiguedad}
          <th>Total</th>
        </tr>
      </thead>
      <tbody>
        {"".join(filas_html)}
      </tbody>
    </table>
    """


def render_fallas():
    tooltip = ("Cantidad de tickets de fallas ABIERTOS (no cerrados) por camión, según "
               "prioridad -- de toda la historia de la cuenta, no solo de los últimos días "
               "(menú Tickets de Datascope).")
    st.markdown(
        f"<h4 title='{tooltip}' style='margin:4px 0 6px 0; text-align:left; font-weight:600; "
        f"font-size:15px; cursor:help;'>⚠️ Fallas</h4>",
        unsafe_allow_html=True,
    )

    todas_patentes = queries.opciones_patentes(engine)
    default_patentes = todas_patentes.loc[todas_patentes["activo"], "patente"].tolist()
    tabla = queries.matriz_fallas(engine, patentes=default_patentes)

    if tabla.empty:
        st.info("No hay camiones seleccionados.")
        return

    st.html(_tabla_fallas_html(tabla))

    st.caption(f"Total de tickets abiertos (todas las prioridades, todos los camiones): **{tabla['Total'].sum()}**")


def render_inspecciones():
    tooltip = ("Por cada día, si se hizo el checklist de Inicio y el de Fin de jornada (por separado). "
               "Clic en un ✅ para ver la foto del reporte.")
    st.markdown(
        f"<h4 title='{tooltip}' style='margin:4px 0 6px 0; text-align:left; font-weight:600; "
        f"font-size:15px; cursor:help;'>🔍 Inspecciones</h4>",
        unsafe_allow_html=True,
    )

    # Letra de los dos filtros proporcional a la de la tabla.
    st.markdown(
        f"""
        <style>
          div[data-testid="stSelectbox"] .react-aria-ComboBox,
          div[data-testid="stSelectbox"] .react-aria-ComboBox *,
          div[data-testid="stMultiSelect"] .react-aria-ComboBox,
          div[data-testid="stMultiSelect"] .react-aria-ComboBox *,
          div[data-testid="stPopover"] button {{
            font-size: {TABLE_FONT_PX}px !important;
          }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Columnas dimensionadas al contenido real (no 50/50) para que Patentes
    # quede pegado a Semana, no repartido a lo ancho de toda la fila.
    ANCHO_SEMANA = TABLE_WIDTH_PX // 2
    ANCHO_PATENTES_BOTON = 170
    col_semana, col_patentes = st.columns(
        [ANCHO_SEMANA, ANCHO_PATENTES_BOTON], gap="small",
        width=ANCHO_SEMANA + ANCHO_PATENTES_BOTON + 16,
    )

    with col_semana:
        opciones = queries.opciones_semana()
        idx = st.selectbox(
            "Semana", options=range(len(opciones)), format_func=lambda i: opciones[i][1],
            key="semana_inspecciones", width=ANCHO_SEMANA,
        )
        semana_inicio = opciones[idx][0]

    with col_patentes:
        todas_patentes = queries.opciones_patentes(engine)
        default_patentes = todas_patentes.loc[todas_patentes["activo"], "patente"].tolist()
        nombre_por_patente = dict(zip(todas_patentes["patente"], todas_patentes["nombre_corto"]))
        # Botón compacto (como el de Semana) que abre un desplegable con el
        # multiselect real -- así las patentes no quedan siempre visibles.
        n_sel = len(st.session_state.get("patentes_inspecciones", default_patentes))
        # Semana tiene una etiqueta arriba que el botón del popover no tiene
        # -- este espacio los deja a la misma altura visual.
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        with st.popover(f"Patentes ({n_sel}) ▾", width=ANCHO_PATENTES_BOTON):
            patentes_sel = st.multiselect(
                "Patentes",
                options=todas_patentes["patente"].tolist(),
                default=default_patentes,
                format_func=lambda p: nombre_por_patente.get(p, p),
                key="patentes_inspecciones",
                label_visibility="collapsed",
            )

    if not patentes_sel:
        st.info("Selecciona al menos una patente.")
        return

    diaria = queries.matriz_cumplimiento_diario(engine, semana_inicio=semana_inicio, patentes=patentes_sel)
    semanal = queries.semanal_ultimas_semanas_cerradas(
        engine, n_semanas=2, semana_referencia=semana_inicio, patentes=patentes_sel,
    )

    if diaria.empty:
        st.info("No hay camiones seleccionados.")
        return

    tabla = diaria.merge(semanal, on="patente", how="left")
    st.html(_tabla_html(tabla, semana_inicio))

    total_realizados = tabla["realizados"].sum()
    total_esperados = tabla["esperados"].sum()
    if total_esperados:
        pct_total = total_realizados / total_esperados * 100
        st.caption(
            f"**Cumplimiento total de la semana: {pct_total:.0f}%** "
            f"({total_realizados}/{total_esperados} checklists realizados)"
        )
    else:
        st.caption("Sin checklists esperados en esta semana para los camiones seleccionados.")


col_inspecciones, col_fallas = st.columns(
    [TABLE_WIDTH_PX, FALLAS_WIDTH_PX], gap="small",
    width=TABLE_WIDTH_PX + FALLAS_WIDTH_PX + 16,
)
with col_inspecciones:
    render_inspecciones()
with col_fallas:
    render_fallas()

st.divider()

col3, col4 = st.columns(2)

with col3:
    st.header("🛠️ Mantenimiento Programado")
    st.info("Próximamente.")

with col4:
    st.header("📦 Inventario")
    st.info("Próximamente.")
