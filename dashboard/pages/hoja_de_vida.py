"""Hoja de Vida - Intub

Historial de Inspecciones, Fallas y Mantenimiento Programado de cada
camión -- 3 secciones independientes -- con Certificado de Mantención
(PDF) descargable para cada registro. Lee lo que ya se completó en el
Software de Mantenimiento, no es una fuente de datos nueva.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

from src import auth, certificado, hoja_de_vida as hv
from src.bootstrap import get_engine
from src.queries import opciones_patentes

engine = get_engine()
usuario = auth.requerir_login(rol_requerido=auth.ROLES_OPERACION)

st.markdown("<h1 style='text-align:center;'>📖 Hoja de Vida</h1>", unsafe_allow_html=True)

todas_patentes = opciones_patentes(engine)
nombre_por_patente = dict(zip(todas_patentes["patente"], todas_patentes["nombre_corto"]))

patente = st.selectbox(
    "Camión", options=todas_patentes["patente"].tolist(),
    format_func=lambda p: f"{nombre_por_patente.get(p, p)} ({p})",
    key="hv_patente",
)
nombre_corto = nombre_por_patente.get(patente, patente)


def _fecha(valor) -> str:
    return valor.strftime("%d-%m-%Y %H:%M") if pd.notna(valor) else "—"


def _texto(valor) -> str | None:
    return valor if pd.notna(valor) and str(valor).strip() else None


def _boton_certificado(ot_item_id: int, key_prefix: str):
    """Generar-y-descargar en 2 pasos: no vale la pena armar el PDF de
    cada fila con solo mostrar la lista, así que se genera recién cuando
    el Jefe lo pide.
    """
    cert_key = f"_cert_bytes_{ot_item_id}"
    if st.button("📄 Generar certificado", key=f"{key_prefix}_gen"):
        detalle = hv.detalle_item_completo(engine, ot_item_id)
        st.session_state[cert_key] = certificado.generar_certificado(detalle, nombre_corto)
    if cert_key in st.session_state:
        st.download_button(
            "⬇️ Descargar certificado (PDF)", data=st.session_state[cert_key],
            file_name=f"certificado_{ot_item_id}.pdf", mime="application/pdf", key=f"{key_prefix}_dl",
        )


tab_insp, tab_fallas, tab_mant = st.tabs(["🔍 Inspecciones", "⚠️ Fallas", "🛠️ Mantenimiento Programado"])

with tab_insp:
    df_insp = hv.inspecciones_completadas(engine, patente)
    st.caption(f"{len(df_insp)} inspección(es) completada(s) registrada(s) para {nombre_corto}.")
    if df_insp.empty:
        st.info("Todavía no hay inspecciones completadas para este camión.")
    else:
        for _, fila in df_insp.iterrows():
            titulo = f"{fila['referencia']} — {_fecha(fila['completado_at'])} — {fila['completado_por']} ({fila['numero_ot']})"
            with st.expander(titulo):
                notas = _texto(fila["notas_cierre"])
                if notas:
                    st.caption(f"Notas: {notas}")
                _boton_certificado(int(fila["ot_item_id"]), f"insp_{fila['ot_item_id']}")

with tab_fallas:
    df_fallas = hv.fallas_completadas(engine, patente)
    st.caption(f"{len(df_fallas)} falla(s) resuelta(s) registrada(s) para {nombre_corto}.")
    if df_fallas.empty:
        st.info("Todavía no hay fallas resueltas para este camión.")
    else:
        for _, fila in df_fallas.iterrows():
            titulo = f"{fila['descripcion'] or fila['referencia']} — {_fecha(fila['completado_at'])} — {fila['completado_por']} ({fila['numero_ot']})"
            with st.expander(titulo):
                sistema = _texto(fila.get("sistema"))
                if sistema:
                    st.caption(f"Sistema trabajado: {sistema}")
                notas = _texto(fila["notas_cierre"])
                if notas:
                    st.caption(f"Notas: {notas}")
                _boton_certificado(int(fila["ot_item_id"]), f"falla_{fila['ot_item_id']}")

with tab_mant:
    df_mant = hv.mantenimientos_completados(engine, patente)
    st.caption(f"{len(df_mant)} mantención(es) completada(s) registrada(s) para {nombre_corto}.")
    if df_mant.empty:
        st.info("Todavía no hay mantenciones completadas para este camión.")
    else:
        for _, fila in df_mant.iterrows():
            titulo = f"{fila['descripcion'] or fila['referencia']} — {_fecha(fila['completado_at'])} — {fila['completado_por']} ({fila['numero_ot']})"
            with st.expander(titulo):
                notas = _texto(fila["notas_cierre"])
                if notas:
                    st.caption(f"Notas: {notas}")
                _boton_certificado(int(fila["ot_item_id"]), f"mant_{fila['ot_item_id']}")
