"""Certificado de Mantenimiento: un PDF formal por cada registro completado
(una Inspección, una Falla resuelta, o un componente de Mantenimiento
Programado), para dejar constancia en la Hoja de Vida del camión.

Usa fpdf2 (puro Python, sin dependencias de sistema) -- no hay logo oficial
de Intub disponible en el proyecto, así que el encabezado usa el nombre en
texto con el mismo color de acento que el resto del software.
"""
from datetime import datetime
from pathlib import Path

from fpdf import FPDF

from src import ot_checklist

_AZUL = (27, 73, 101)
_GRIS = (90, 90, 90)
_GRIS_CLARO = (230, 233, 236)

TIPO_ITEM_TITULO = {
    "inspeccion": "Certificado de Inspección",
    "ticket": "Certificado de Resolución de Falla",
    "item_key": "Certificado de Mantención Programada",
}


class _CertificadoPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 18)
        self.set_text_color(*_AZUL)
        self.cell(0, 10, "INTUB", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*_GRIS)
        self.set_y(12)
        self.cell(0, 6, f"Emitido: {datetime.now().strftime('%d-%m-%Y %H:%M')}", align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*_AZUL)
        self.set_line_width(0.6)
        self.line(10, 22, 200, 22)
        self.ln(8)

    def footer(self):
        self.set_y(-18)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*_GRIS)
        self.cell(0, 5, "Documento generado automáticamente por el Software de Mantenimiento de Intub.", align="C", new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 5, f"Página {self.page_no()}", align="C")


def _fila_dato(pdf, etiqueta, valor):
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*_GRIS)
    pdf.cell(45, 7, etiqueta)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(20, 20, 20)
    # new_x/new_y explícitos: por defecto multi_cell deja el cursor donde
    # terminó de escribir (no en el margen izquierdo), así que sin esto la
    # siguiente fila se intenta dibujar fuera de la página.
    pdf.multi_cell(0, 7, valor or "—", new_x="LMARGIN", new_y="NEXT")


def _titulo_seccion(pdf, texto):
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*_AZUL)
    pdf.cell(0, 8, texto, new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*_GRIS_CLARO)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(2)


def _agregar_foto(pdf, ruta_relativa, etiqueta, ancho=85):
    if not ruta_relativa:
        return
    ruta = ot_checklist.ruta_absoluta(ruta_relativa)
    if not Path(ruta).exists():
        return
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*_GRIS)
    pdf.cell(ancho, 6, etiqueta, new_x="LMARGIN", new_y="NEXT")
    try:
        pdf.image(str(ruta), w=ancho)
    except Exception:  # noqa: BLE001 -- una foto corrupta no debe tumbar el certificado
        pdf.set_font("Helvetica", "I", 8)
        pdf.cell(ancho, 6, "(no se pudo cargar la imagen)", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)


def generar_certificado(detalle: dict, nombre_corto: str) -> bytes:
    """`detalle` es el dict que arma `hoja_de_vida.detalle_item_completo`.
    Devuelve los bytes del PDF, listos para `st.download_button`.
    """
    pdf = _CertificadoPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=22)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(20, 20, 20)
    pdf.cell(0, 10, TIPO_ITEM_TITULO.get(detalle["tipo_item"], "Certificado de Mantenimiento"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    _titulo_seccion(pdf, "Datos generales")
    _fila_dato(pdf, "Camión", f"{nombre_corto} ({detalle['patente']})")
    _fila_dato(pdf, "Orden de Trabajo", detalle["numero_ot"])
    _fila_dato(pdf, "Ítem", detalle["descripcion"] or detalle["referencia"])
    _fila_dato(pdf, "Realizado por", detalle["completado_por"])
    completado_at = detalle["completado_at"]
    _fila_dato(pdf, "Fecha de ejecución", completado_at.strftime("%d-%m-%Y %H:%M") if completado_at else "—")
    _fila_dato(pdf, "Solicitado por", detalle["creado_por"])

    if detalle["tipo_item"] == "inspeccion":
        _titulo_seccion(pdf, f"Checklist: {detalle['referencia']}")
        checklist = detalle["checklist"]
        grupo_anterior = None
        for _, fila in checklist.iterrows():
            if fila["grupo"] != grupo_anterior:
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(*_AZUL)
                pdf.cell(0, 7, fila["grupo"], new_x="LMARGIN", new_y="NEXT")
                grupo_anterior = fila["grupo"]
            estado_txt = ot_checklist.ESTADO_LABEL.get(fila["estado"], fila["estado"])
            if fila["estado"] == "fuera_normal":
                color = (176, 46, 38)
            elif fila["estado"] == "no_aplica":
                color = (150, 120, 20)
            else:
                color = (44, 122, 78)
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(20, 20, 20)
            pdf.cell(90, 6, fila["item"])
            pdf.set_text_color(*color)
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 6, estado_txt, new_x="LMARGIN", new_y="NEXT")
            if fila["estado"] in ("fuera_normal", "no_aplica") and fila["observacion"]:
                pdf.set_font("Helvetica", "I", 9)
                pdf.set_text_color(*_GRIS)
                pdf.multi_cell(0, 5, f"   {fila['observacion']}", new_x="LMARGIN", new_y="NEXT")
        _titulo_seccion(pdf, "Fotos de respaldo")
        for _, fila in checklist.iterrows():
            _agregar_foto(pdf, fila["foto_ruta"], fila["item"], ancho=70)

    elif detalle["tipo_item"] == "ticket":
        _titulo_seccion(pdf, "Detalle de la falla")
        ticket = detalle.get("ticket") or {}
        _fila_dato(pdf, "N° ticket Datascope", f"#{ticket.get('code', '—')}")
        _fila_dato(pdf, "Descripción original", ticket.get("description") or ticket.get("name") or "—")
        _fila_dato(pdf, "Sistema trabajado", detalle.get("sistema"))
        _fila_dato(pdf, "Notas de cierre", detalle.get("notas_cierre"))
        fotos = detalle["fotos"]
        _titulo_seccion(pdf, "Fotos")
        antes = fotos[fotos["momento"] == "antes"]
        despues = fotos[fotos["momento"] == "despues"]
        if not antes.empty:
            _agregar_foto(pdf, antes.iloc[0]["ruta"], "Antes")
        if not despues.empty:
            _agregar_foto(pdf, despues.iloc[0]["ruta"], "Después")

    elif detalle["tipo_item"] == "item_key":
        _titulo_seccion(pdf, "Detalle de la mantención")
        _fila_dato(pdf, "Componente", detalle["descripcion"] or detalle["referencia"])
        if detalle.get("horometro") is not None:
            _fila_dato(pdf, "Horómetro", f"{detalle['horometro']} h")
        _fila_dato(pdf, "Notas de cierre", detalle.get("notas_cierre"))
        fotos = detalle["fotos"]
        _titulo_seccion(pdf, "Fotos")
        antes = fotos[fotos["momento"] == "antes"]
        despues = fotos[fotos["momento"] == "despues"]
        if not antes.empty:
            _agregar_foto(pdf, antes.iloc[0]["ruta"], "Antes")
        if not despues.empty:
            _agregar_foto(pdf, despues.iloc[0]["ruta"], "Después")

    pdf.ln(10)
    _titulo_seccion(pdf, "Firmas")
    y_firma = pdf.get_y() + 15
    pdf.line(20, y_firma, 90, y_firma)
    pdf.line(120, y_firma, 190, y_firma)
    pdf.set_y(y_firma + 1)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*_GRIS)
    pdf.cell(90, 5, "Mecánico responsable", align="C")
    pdf.cell(0, 5, "Jefe de Mantención", align="C")

    return bytes(pdf.output())
