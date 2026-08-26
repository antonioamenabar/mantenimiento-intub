"""Dashboard de Mantenimiento - Intub (solo lectura)
4 cuadrantes: Inspecciones | Fallas | Mantenimiento Programado | Inventario

Esta página NO registra nada -- para crear y asignar trabajo, ver
"Software de Mantenimiento". Para completar una OT asignada, ver "Mis OTs".
"""
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from src import auth, queries, planificacion
from src.bootstrap import get_engine

st.set_page_config(page_title="Dashboard Mantenimiento - Intub", layout="wide")

engine = get_engine()
auth.requerir_login(rol_requerido=auth.ROLES_GESTION)

st.markdown(
    """
    <style>
      .block-container { padding-top: 1rem !important; }
    </style>
    <h1 style='text-align:center; margin-top:0;'>🚛 Dashboard de Mantenimiento</h1>
    """,
    unsafe_allow_html=True,
)

# Ancho objetivo de la tabla de Inspecciones (~1/2 de una pantalla de
# escritorio típica). Los filtros de arriba se fuerzan al mismo ancho (o la
# mitad, para el de semana) para que quede todo alineado.
TABLE_WIDTH_PX = 620
TABLE_FONT_PX = 12
# Ancho de la tabla de Fallas, pensado para quedar al lado de Inspecciones
# (no debajo), con columnas al mínimo para que quepa todo sin scroll.
FALLAS_WIDTH_PX = 460

# Colores por estado de vencimiento en la matriz de Mantenimiento Programado
# (mismo criterio en ambos temas -- claro/oscuro -- porque son colores fijos
# de estado, no del tema de Streamlit).
_COLOR_ESTADO = {
    "ok": ("#2F7D50", "#E3F0E7"),
    "proximo": ("#9B6B0C", "#F5EBD3"),
    "vencido": ("#A6423B", "#F4E1DE"),
    "sin_evento": ("#8A97A3", "#EBEDEF"),
    "sin_regla": ("#8A97A3", "#EBEDEF"),
}


@st.dialog("Detalle de tickets")
def _dialog_detalle_fallas(patente: str, prioridad_key: str, bucket: str):
    nombre = queries.opciones_patentes(engine)
    nombre = dict(zip(nombre["patente"], nombre["nombre_corto"])).get(patente, patente)
    st.markdown(
        f"**{nombre}** ({patente}) — {queries.PRIORIDAD_LABEL.get(prioridad_key, prioridad_key)} — {bucket}"
    )
    detalle = queries.detalle_fallas(engine, patente, prioridad_key, bucket)
    if detalle.empty:
        st.info("No hay tickets en este rango.")
    else:
        st.dataframe(detalle, hide_index=True, width="stretch")
    if st.button("Cerrar"):
        st.query_params.clear()
        st.rerun()


def _revisar_query_params_fallas():
    """Si la URL tiene ?falla_detalle=PATENTE|PRIORIDAD|CLAVE_ANTIGUEDAD (por
    haber hecho clic en un número de la tabla de Fallas), abre el popup con
    el detalle. Clic en la tabla = cambio de query param = rerun de
    Streamlit, sin abrir pestaña ni ventana nueva.
    """
    valor = st.query_params.get("falla_detalle")
    if not valor:
        return
    try:
        patente, prioridad_key, bucket_key = valor.split("|")
        bucket = queries.ANTIGUEDAD_KEY_INV[bucket_key]
    except (ValueError, KeyError):
        st.query_params.clear()
        return
    _dialog_detalle_fallas(patente, prioridad_key, bucket)


@st.dialog("Historial de mantención")
def _dialog_detalle_mantenimiento(patente: str, item_key: str):
    nombre = dict(zip(
        queries.opciones_patentes(engine)["patente"], queries.opciones_patentes(engine)["nombre_corto"]
    )).get(patente, patente)
    items = planificacion.catalogo_items(engine)
    nombre_item = dict(zip(items["item_key"], items["nombre"])).get(item_key, item_key)
    st.markdown(f"**{nombre}** ({patente}) — {nombre_item}")
    historial = planificacion.historial_evento(engine, patente, item_key)
    if historial.empty:
        st.info("Todavía no se ha registrado ninguna mantención de este ítem en este camión.")
    else:
        st.dataframe(historial, hide_index=True, width="stretch")
    if st.button("Cerrar", key="cerrar_detalle_mant"):
        st.query_params.clear()
        st.rerun()


def _revisar_query_params_mantenimiento():
    """Análogo a `_revisar_query_params_fallas`: ?mant_detalle=PATENTE|ITEM_KEY
    abre el historial de ese ítem en un popup, sin pestaña nueva.
    """
    valor = st.query_params.get("mant_detalle")
    if not valor:
        return
    try:
        patente, item_key = valor.split("|")
    except ValueError:
        st.query_params.clear()
        return
    _dialog_detalle_mantenimiento(patente, item_key)


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


_COLOR_PRIORIDAD = {"Crítica": "#d32f2f", "Alta": "#f57c00", "Media": "#fbc02d", "Baja": "#388e3c"}
_PRIORIDAD_LABEL_A_KEY = {v: k for k, v in queries.PRIORIDAD_LABEL.items()}
_ANTIGUEDAD_CORTO = {"Menos de 7 días": "<7", "Entre 8 y 21 días": "8-21", "Más de 21 días": ">21"}


def _celda_fallas(valor: int, patente: str, prioridad_label: str, bucket: str, clickeable: bool) -> str:
    if valor and clickeable:
        prioridad_key = _PRIORIDAD_LABEL_A_KEY[prioridad_label]
        bucket_key = queries.ANTIGUEDAD_KEY[bucket]
        href = f"?falla_detalle={patente}|{prioridad_key}|{bucket_key}"
        return f'<a href="{href}" title="Ver detalle">{valor}</a>'
    return str(valor)


def _tabla_fallas_html(tabla, en_vivo: bool) -> str:
    """Tabla HTML propia para Fallas: Patente, Camión, y para cada prioridad
    (Crítica/Alta/Media/Baja) 3 columnas de antigüedad (<7 / 8-21 / >21
    días), más el Total. Los números > 0 son un link que abre el detalle en
    un popup (st.dialog) -- solo si `en_vivo` (el histórico no guarda
    detalle ticket a ticket).
    """
    cols_prioridad = list(queries.PRIORIDAD_LABEL.values())
    cols_antiguedad = queries.ANTIGUEDAD_BUCKETS

    filas_html = []
    for _, row in tabla.iterrows():
        celdas = "".join(
            f"<td class='num'>{_celda_fallas(row[queries._col_cruzada(p, b)], row['patente'], p, b, en_vivo)}</td>"
            for p in cols_prioridad for b in cols_antiguedad
        )
        filas_html.append(
            "<tr>"
            f"<td class='patente'>{row['patente']}</td>"
            f"<td class='nombre'>{row['nombre_corto']}</td>"
            f"{celdas}"
            f"<td class='num total'>{row['Total']}</td>"
            "</tr>"
        )

    head_prioridad = "".join(
        f"<th colspan='3' style='color:{_COLOR_PRIORIDAD[p]}'>{p}</th>" for p in cols_prioridad
    )
    head_antiguedad = "".join(
        f"<th>{_ANTIGUEDAD_CORTO[b]}</th>" for _ in cols_prioridad for b in cols_antiguedad
    )

    return f"""
    <style>
      .tabla-fallas {{
        border-collapse: collapse; font-size: 12px; width: {FALLAS_WIDTH_PX}px;
      }}
      .tabla-fallas th, .tabla-fallas td {{
        border: 1px solid rgba(128,128,128,0.35);
        padding: 2px 3px;
        text-align: center;
        white-space: nowrap;
        line-height: 1.2;
        box-sizing: border-box;
      }}
      .tabla-fallas td.num {{ width: 21px; }}
      .tabla-fallas td.total {{ font-weight: 600; }}
      .tabla-fallas td.nombre, .tabla-fallas td.patente {{ text-align: left; font-weight: 500; }}
      .tabla-fallas td.patente {{ opacity: 0.7; font-size: 11px; width: 46px; }}
      .tabla-fallas td.nombre {{ width: 62px; }}
      .tabla-fallas a {{ text-decoration: none; font-weight: 600; }}
      .tabla-fallas thead th {{
        background: rgba(128,128,128,0.12); font-size: 10px; font-weight: 700;
      }}
    </style>
    <table class="tabla-fallas">
      <thead>
        <tr>
          <th rowspan="2">Patente</th>
          <th rowspan="2">Camión</th>
          {head_prioridad}
          <th rowspan="2">Total</th>
        </tr>
        <tr>{head_antiguedad}</tr>
      </thead>
      <tbody>
        {"".join(filas_html)}
      </tbody>
    </table>
    """


def render_fallas():
    tooltip = ("Cantidad de tickets de fallas ABIERTOS (no cerrados) por camión, según "
               "prioridad. La semana actual se calcula en vivo; las semanas pasadas muestran "
               "la foto guardada el lunes siguiente (menú Tickets de Datascope).")

    # Mismo st.markdown "vacío" que en Inspecciones, para que la fila del
    # título quede a la misma altura en ambos cuadrantes.
    st.markdown("<style></style>", unsafe_allow_html=True)

    ANCHO_SEMANA = FALLAS_WIDTH_PX // 2
    ANCHO_PATENTES_BOTON = FALLAS_WIDTH_PX // 2
    TITULO_W = 150
    col_titulo, col_semana, col_patentes = st.columns(
        [TITULO_W, ANCHO_SEMANA, ANCHO_PATENTES_BOTON], gap="small",
        vertical_alignment="center",
        width=TITULO_W + ANCHO_SEMANA + ANCHO_PATENTES_BOTON + 32,
    )

    with col_titulo:
        st.markdown(
            f"<h4 title='{tooltip}' style='margin:0; text-align:left; font-weight:600; "
            f"font-size:15px; cursor:help;'>⚠️ Fallas</h4>",
            unsafe_allow_html=True,
        )

    opciones = queries.opciones_semana()
    todas_patentes = queries.opciones_patentes(engine)
    default_patentes = todas_patentes.loc[todas_patentes["activo"], "patente"].tolist()
    nombre_por_patente = dict(zip(todas_patentes["patente"], todas_patentes["nombre_corto"]))

    with col_semana:
        idx = st.selectbox(
            "Semana", options=range(len(opciones)), format_func=lambda i: f"Semana: {opciones[i][1]}",
            key="semana_fallas", width=ANCHO_SEMANA, label_visibility="collapsed",
        )
        semana_inicio = opciones[idx][0]

    with col_patentes:
        n_sel = len(st.session_state.get("patentes_fallas", default_patentes))
        with st.popover(f"Patentes ({n_sel}) ▾", width=ANCHO_PATENTES_BOTON):
            patentes_sel = st.multiselect(
                "Patentes",
                options=todas_patentes["patente"].tolist(),
                default=default_patentes,
                format_func=lambda p: nombre_por_patente.get(p, p),
                key="patentes_fallas",
                label_visibility="collapsed",
            )

    if not patentes_sel:
        st.info("Selecciona al menos una patente.")
        return

    tabla, en_vivo = queries.matriz_fallas_semana(engine, semana_inicio, patentes=patentes_sel)

    if tabla.empty:
        st.info("Todavía no hay una foto histórica guardada para esta semana "
                "(se guarda automáticamente el lunes siguiente a las 8:00 AM).")
        return

    st.html(_tabla_fallas_html(tabla, en_vivo))

    etiqueta_vivo = "en vivo" if en_vivo else "foto del lunes"
    st.caption(
        f"Total de tickets abiertos ({etiqueta_vivo}, todas las prioridades): **{tabla['Total'].sum()}**"
    )


def _celda_mantenimiento(info: dict, patente: str, item_key: str) -> str:
    color, fondo = _COLOR_ESTADO.get(info["estado"], _COLOR_ESTADO["sin_evento"])
    href = f"?mant_detalle={patente}|{item_key}"
    return (
        f"<td class='celda' style='background:{fondo}; color:{color};' "
        f"title='Confianza de la regla: {planificacion.CONFIANZA_LABEL.get(info['confianza'], info['confianza'])}'>"
        f"<a href='{href}'>{info['texto']}</a></td>"
    )


def _tabla_mantenimiento_html(tabla, items_df) -> str:
    """Tabla HTML propia para Mantenimiento Programado: Patente, Camión, y
    2 grupos de columnas (Camión / Equipo), una por ítem del catálogo. Cada
    celda es un link que abre el historial de ese ítem en ese camión.
    """
    camion_items = items_df[items_df["categoria"] == "camion"].to_dict("records")
    equipo_items = items_df[items_df["categoria"] == "equipo"].to_dict("records")
    todos_items = camion_items + equipo_items

    filas_html = []
    for _, row in tabla.iterrows():
        celdas = "".join(
            _celda_mantenimiento(row[it["item_key"]], row["patente"], it["item_key"])
            for it in todos_items
        )
        filas_html.append(
            "<tr>"
            f"<td class='patente'>{row['patente']}</td>"
            f"<td class='nombre'>{row['nombre_corto']}</td>"
            f"{celdas}"
            "</tr>"
        )

    head_camion = "".join(f"<th>{it['nombre']}</th>" for it in camion_items)
    head_equipo = "".join(f"<th>{it['nombre']}</th>" for it in equipo_items)

    return f"""
    <div style="overflow-x:auto;">
    <style>
      .tabla-mant {{
        border-collapse: collapse; font-size: 11px; white-space: nowrap;
      }}
      .tabla-mant th, .tabla-mant td {{
        border: 1px solid rgba(128,128,128,0.35);
        padding: 3px 5px;
        text-align: center;
        line-height: 1.2;
        box-sizing: border-box;
      }}
      .tabla-mant td.nombre, .tabla-mant td.patente {{ text-align: left; font-weight: 500; }}
      .tabla-mant td.patente {{ opacity: 0.7; font-size: 10px; }}
      .tabla-mant a {{ text-decoration: none; color: inherit; font-weight: 600; }}
      .tabla-mant thead th {{ font-size: 10px; font-weight: 700; }}
      .tabla-mant thead tr:first-child th.grupo-camion {{ background: rgba(27,73,101,0.18); }}
      .tabla-mant thead tr:first-child th.grupo-equipo {{ background: rgba(155,107,12,0.18); }}
      .tabla-mant thead tr:last-child th {{ background: rgba(128,128,128,0.12); }}
    </style>
    <table class="tabla-mant">
      <thead>
        <tr>
          <th rowspan="2">Patente</th>
          <th rowspan="2">Camión</th>
          <th class="grupo-camion" colspan="{len(camion_items)}">CAMIÓN (chasis)</th>
          <th class="grupo-equipo" colspan="{len(equipo_items)}">EQUIPO</th>
        </tr>
        <tr>{head_camion}{head_equipo}</tr>
      </thead>
      <tbody>
        {"".join(filas_html)}
      </tbody>
    </table>
    </div>
    """


def render_mantenimiento_programado():
    tooltip = ("Próxima fecha de mantención de cada componente mayor, por camión. "
               "Verde = OK, Amarillo = próximo (30 días o menos), Rojo = vencido, "
               "Gris = todavía no se ha registrado ninguna mantención. Clic en una "
               "celda para ver el historial. Para crear trabajo nuevo, usa el "
               "Software de Mantenimiento (menú de la izquierda).")

    st.markdown(
        f"<h4 title='{tooltip}' style='margin:0; font-weight:600; font-size:15px; cursor:help;'>"
        f"🛠️ Mantenimiento Programado</h4>",
        unsafe_allow_html=True,
    )

    todas_patentes = queries.opciones_patentes(engine)
    default_patentes = todas_patentes.loc[todas_patentes["activo"], "patente"].tolist()
    nombre_por_patente = dict(zip(todas_patentes["patente"], todas_patentes["nombre_corto"]))

    n_sel = len(st.session_state.get("patentes_mant", default_patentes))
    with st.popover(f"Patentes ({n_sel}) ▾"):
        patentes_sel = st.multiselect(
            "Patentes",
            options=todas_patentes["patente"].tolist(),
            default=default_patentes,
            format_func=lambda p: nombre_por_patente.get(p, p),
            key="patentes_mant",
            label_visibility="collapsed",
        )

    if not patentes_sel:
        st.info("Selecciona al menos una patente.")
        return

    items_df = planificacion.catalogo_items(engine)
    tabla = planificacion.matriz_mantenimiento(engine, patentes=patentes_sel)

    if tabla.empty:
        st.info("No hay camiones seleccionados.")
        return

    st.html(_tabla_mantenimiento_html(tabla, items_df))

    vencidos = sum(1 for _, row in tabla.iterrows() for it in items_df["item_key"] if row[it]["estado"] == "vencido")
    proximos = sum(1 for _, row in tabla.iterrows() for it in items_df["item_key"] if row[it]["estado"] == "proximo")
    st.caption(
        f"**{vencidos} vencidos · {proximos} próximos** en los componentes seleccionados. "
        "Todavía no hay fechas de partida para la mayoría de los ítems -- se activan a medida "
        "que se completan OTs de Mantenimiento Programado."
    )


def render_inspecciones():
    tooltip = ("Por cada día, si se hizo el checklist de Inicio y el de Fin de jornada (por separado). "
               "Clic en un ✅ para ver la foto del reporte.")

    # Letra de los filtros proporcional a la de la tabla (aplica a los de
    # Inspecciones y Fallas por igual, ya que la regla es global).
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

    # Título y los dos filtros (mismo ancho entre ellos, y juntos respetan
    # el ancho de la tabla) en una sola fila.
    ANCHO_SEMANA = TABLE_WIDTH_PX // 2
    ANCHO_PATENTES_BOTON = TABLE_WIDTH_PX // 2
    TITULO_W = 150
    col_titulo, col_semana, col_patentes = st.columns(
        [TITULO_W, ANCHO_SEMANA, ANCHO_PATENTES_BOTON], gap="small",
        vertical_alignment="center",
        width=TITULO_W + ANCHO_SEMANA + ANCHO_PATENTES_BOTON + 32,
    )

    with col_titulo:
        st.markdown(
            f"<h4 title='{tooltip}' style='margin:0; text-align:left; font-weight:600; "
            f"font-size:15px; cursor:help;'>🔍 Inspecciones</h4>",
            unsafe_allow_html=True,
        )

    opciones = queries.opciones_semana()
    todas_patentes = queries.opciones_patentes(engine)
    default_patentes = todas_patentes.loc[todas_patentes["activo"], "patente"].tolist()
    nombre_por_patente = dict(zip(todas_patentes["patente"], todas_patentes["nombre_corto"]))

    with col_semana:
        idx = st.selectbox(
            "Semana", options=range(len(opciones)), format_func=lambda i: f"Semana: {opciones[i][1]}",
            key="semana_inspecciones", width=ANCHO_SEMANA, label_visibility="collapsed",
        )
        semana_inicio = opciones[idx][0]

    with col_patentes:
        # Botón compacto (como el de Semana) que abre un desplegable con el
        # multiselect real -- así las patentes no quedan siempre visibles.
        n_sel = len(st.session_state.get("patentes_inspecciones", default_patentes))
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


_revisar_query_params_fallas()
_revisar_query_params_mantenimiento()

GAP_ENTRE_CUADRANTES = 50
col_inspecciones, col_fallas = st.columns(
    [TABLE_WIDTH_PX, FALLAS_WIDTH_PX], gap=GAP_ENTRE_CUADRANTES,
    width=TABLE_WIDTH_PX + FALLAS_WIDTH_PX + GAP_ENTRE_CUADRANTES,
)
with col_inspecciones:
    render_inspecciones()
with col_fallas:
    render_fallas()

st.divider()

col3, col4 = st.columns(2)

with col3:
    render_mantenimiento_programado()

with col4:
    st.header("📦 Inventario")
    st.info("Próximamente.")
