"""Dashboard de Mantenimiento - Intub (solo lectura)
4 cuadrantes: Inspecciones | Fallas | Mantenimiento Programado | Inventario

Esta página NO registra nada -- para crear y asignar trabajo, ver
"Crear OT" (dentro de Software). Para completar una OT asignada, ver "Mis OTs".
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

from src import auth, db, queries, planificacion
from src.bootstrap import get_engine

engine = get_engine()
usuario = auth.requerir_login(rol_requerido=auth.ROLES_OPERACION)

# Aviso de "fallas nuevas desde tu última visita" -- se calcula una sola vez
# por sesión (al entrar/recargar la página), no en cada rerun por clic,
# para que no desaparezca ni se recalcule mientras navegas el resto del
# Dashboard en la misma sesión.
if "fallas_nuevas_aviso" not in st.session_state:
    desde = db.obtener_ultima_vista_fallas(engine, usuario["id"])
    st.session_state["fallas_nuevas_aviso"] = queries.fallas_nuevas_desde(engine, desde)
    db.marcar_vista_fallas(engine, usuario["id"], datetime.now())

_fallas_nuevas = st.session_state["fallas_nuevas_aviso"]
if not _fallas_nuevas.empty:
    _patentes_txt = ", ".join(sorted(_fallas_nuevas["patente"].dropna().unique()))
    st.warning(f"🔧 **{len(_fallas_nuevas)} falla(s) nueva(s)** desde tu última visita: {_patentes_txt}")

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
# Ancho "objetivo" de la TABLA de Fallas en sí (st.dataframe, 15 columnas:
# Patente + Camión + 4 prioridades x 3 antigüedades + Total) -- distinto de
# FALLAS_WIDTH_PX (que solo dimensiona los filtros de arriba). Es la
# proporción que se le pide a st.columns, no un límite duro: la fila ya no
# fuerza un ancho total fijo, se estira con la ventana real (ver el
# st.columns de más abajo) -- probado a mano en ventanas de 1280 a 1920px
# de ancho para que las 15 columnas se vean sin scroll interno.
FALLAS_TABLE_WIDTH_PX = 1150

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
        # Limpia la selección de la celda en la tabla (no query params -- el
        # clic en la celda usa la selección nativa de st.dataframe, ver
        # `render_fallas`) para que el popup no se vuelva a abrir solo en el
        # próximo rerun.
        st.session_state["tabla_fallas_sel"] = {"selection": {"rows": [], "columns": [], "cells": []}}
        st.rerun()


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
        st.session_state["tabla_mant_sel"] = {"selection": {"rows": [], "columns": [], "cells": []}}
        st.rerun()


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


_PRIORIDAD_LABEL_A_KEY = {v: k for k, v in queries.PRIORIDAD_LABEL.items()}
_ANTIGUEDAD_CORTO = {"Menos de 7 días": "<7", "Entre 8 y 21 días": "8-21", "Más de 21 días": ">21"}
_COLOR_PRIORIDAD_BG = {
    "Crítica": "rgba(211,47,47,0.14)",
    "Alta": "rgba(245,124,0,0.14)",
    "Media": "rgba(251,192,0,0.16)",
    "Baja": "rgba(56,142,60,0.14)",
}


def render_fallas():
    tooltip = ("Cantidad de tickets de fallas ABIERTOS (no cerrados) por camión, según "
               "prioridad. La semana actual se calcula en vivo -- clic en un número para ver "
               "el detalle. Las semanas pasadas muestran la foto guardada el lunes siguiente "
               "(menú Tickets de Datascope) y no tienen detalle clickeable.")

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

    cols_prioridad = list(queries.PRIORIDAD_LABEL.values())
    cols_antiguedad = queries.ANTIGUEDAD_BUCKETS
    # Mismo formato que `queries._col_cruzada` -- son los nombres de columna
    # que ya vienen armados en `tabla`.
    cols_cruzadas = [f"{p}||{b}" for p in cols_prioridad for b in cols_antiguedad]

    df_vista = tabla[["patente", "nombre_corto"] + cols_cruzadas + ["Total"]].reset_index(drop=True)

    # Anchos en pixeles (no "small"/"medium") -- son 15 columnas en total y
    # necesitan quedar bien compactas para que quepan sin scroll interno en
    # una ventana de escritorio normal (probado a mano de 1280 a 1920px).
    # El emoji de prioridad se sacó del encabezado (no entraba junto con el
    # texto de antigüedad en un ancho tan chico) -- la agrupación por
    # prioridad la da el color de fondo de `_colorear`, y el detalle
    # completo ("Crítica · Menos de 7 días") queda en el tooltip (`help`).
    column_config = {
        "patente": st.column_config.TextColumn("Patente", width=55),
        "nombre_corto": st.column_config.TextColumn("Camión", width=68),
        "Total": st.column_config.NumberColumn("Total", width=48),
    }
    for p in cols_prioridad:
        for b in cols_antiguedad:
            column_config[f"{p}||{b}"] = st.column_config.NumberColumn(
                _ANTIGUEDAD_CORTO[b], width=31, help=f"{p} · {b}",
            )

    def _colorear(df):
        estilos = pd.DataFrame("", index=df.index, columns=df.columns)
        for p in cols_prioridad:
            for b in cols_antiguedad:
                estilos[f"{p}||{b}"] = f"background-color:{_COLOR_PRIORIDAD_BG[p]}"
        return estilos

    # Clic en una celda de conteo abre el detalle -- selección nativa de
    # st.dataframe (websocket, sin navegación de verdad), no un link HTML:
    # eso último recargaba la página entera y cerraba la sesión (ver
    # historial en el commit df9c48a). Solo clickeable en vivo -- el
    # histórico no guarda detalle ticket a ticket.
    # height="content" (no un número fijo en pixeles): un alto fijo calculado
    # a mano quedó descuadrado apenas Streamlit Cloud resolvió una versión de
    # Streamlit levemente distinta a la de desarrollo (requirements.txt no
    # fija la versión exacta) y recortó la última fila -- "content" siempre
    # se ajusta solo a las filas reales, sin recortar, aunque quede a un par
    # de pixeles de la altura exacta de Inspecciones (imperceptible).
    evento = st.dataframe(
        df_vista.style.apply(_colorear, axis=None),
        hide_index=True, width="stretch",
        column_config=column_config,
        on_select="rerun" if en_vivo else "ignore",
        selection_mode="single-cell",
        key="tabla_fallas_sel",
        row_height=19,
        height="content",
    )

    if en_vivo and evento is not None:
        celdas = evento["selection"]["cells"]
        if celdas:
            fila_idx, col_nombre = celdas[0]
            if col_nombre in cols_cruzadas and df_vista.at[fila_idx, col_nombre]:
                patente = df_vista.at[fila_idx, "patente"]
                prioridad_label, bucket = col_nombre.split("||")
                _dialog_detalle_fallas(patente, _PRIORIDAD_LABEL_A_KEY[prioridad_label], bucket)

    etiqueta_vivo = "en vivo" if en_vivo else "foto del lunes"
    st.caption(
        f"Total de tickets abiertos ({etiqueta_vivo}, todas las prioridades): **{tabla['Total'].sum()}**"
    )


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

    tabla = tabla.reset_index(drop=True)
    camion_items = items_df[items_df["categoria"] == "camion"].to_dict("records")
    equipo_items = items_df[items_df["categoria"] == "equipo"].to_dict("records")
    todos_items = camion_items + equipo_items
    item_keys = [it["item_key"] for it in todos_items]

    df_vista = pd.DataFrame({
        "patente": tabla["patente"],
        "nombre_corto": tabla["nombre_corto"],
        **{key: tabla[key].apply(lambda info: info["texto"]) for key in item_keys},
    })

    column_config = {
        "patente": st.column_config.TextColumn("Patente", width="small"),
        "nombre_corto": st.column_config.TextColumn("Camión", width="small"),
    }
    # 🚛 = ítem del camión (chasis), ⚙️ = ítem del equipo -- reemplaza al
    # agrupamiento de encabezados de la tabla HTML anterior (st.dataframe no
    # soporta encabezados agrupados en varias filas).
    for it in camion_items:
        column_config[it["item_key"]] = st.column_config.TextColumn(f"🚛 {it['nombre']}", width="small")
    for it in equipo_items:
        column_config[it["item_key"]] = st.column_config.TextColumn(f"⚙️ {it['nombre']}", width="small")

    def _colorear(df):
        estilos = pd.DataFrame("", index=df.index, columns=df.columns)
        for key in item_keys:
            for fila_idx in df.index:
                estado = tabla.at[fila_idx, key]["estado"]
                color, fondo = _COLOR_ESTADO.get(estado, _COLOR_ESTADO["sin_evento"])
                estilos.at[fila_idx, key] = f"background-color:{fondo}; color:{color};"
        return estilos

    # Clic en una celda abre el historial de ese ítem en ese camión --
    # selección nativa de st.dataframe, mismo motivo que en `render_fallas`
    # (evitar el <a href="?..."> que recargaba la página y cerraba sesión).
    evento = st.dataframe(
        df_vista.style.apply(_colorear, axis=None),
        hide_index=True, width="stretch",
        column_config=column_config,
        on_select="rerun", selection_mode="single-cell",
        key="tabla_mant_sel",
    )

    if evento is not None:
        celdas = evento["selection"]["cells"]
        if celdas:
            fila_idx, col_nombre = celdas[0]
            if col_nombre in item_keys:
                patente = df_vista.at[fila_idx, "patente"]
                _dialog_detalle_mantenimiento(patente, col_nombre)

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


GAP_ENTRE_CUADRANTES = 50
# Sin `width=` fijo -- width="stretch" es el default de st.columns, así la
# fila usa el ancho real de la ventana del usuario (antes quedaba topada a
# TABLE_WIDTH_PX+FALLAS_WIDTH_PX+gap sin importar cuánta pantalla hubiera
# de sobra, y la tabla de Fallas no tenía dónde mostrar sus 15 columnas).
col_inspecciones, col_fallas = st.columns(
    [TABLE_WIDTH_PX, FALLAS_TABLE_WIDTH_PX], gap=GAP_ENTRE_CUADRANTES,
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
