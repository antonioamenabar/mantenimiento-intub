"""Cliente para la API de Datascope.

Documentación oficial: https://dscope.github.io/docs/
Ojo: existe también "DataScope Select" de LSEG/Refinitiv, que es un producto
financiero totalmente distinto — no confundir la documentación.
"""
from datetime import date, timedelta

import requests

from src import config

BASE_URL = "https://www.mydatascope.com/api/external"

# Sin start/end, la API solo devuelve una ventana reciente por defecto
# (~8 días), no el histórico completo. Además, start/end filtran por la
# fecha de ENVÍO del formulario (created_at), no por "Fecha Inicio Trabajos"
# que llena el mecánico -- por eso pedimos con margen y filtramos por ese
# campo después, en queries.py.
#
# OJO: se probó con una ventana de 60 días en una sola llamada y la API
# devolvió los resultados con un hueco de ~3 semanas en el medio (posible
# límite de resultados por request que trunca de forma no obvia en rangos
# grandes). Con 21 días no se reproduce el problema. Si en el futuro se
# necesita traer más historial, hay que pedirlo en varios llamados de rango
# acotado (ej. por semana) y concatenar, no en un solo llamado grande.
DEFAULT_LOOKBACK_DAYS = 21

# "R-PR02-04 Reporte Faenas en Terreno" y "Reporte Faenas en Terreno
# Vitacura ECC" -- indican si el camión efectivamente salió a trabajar ese
# día. Se usan para saber si corresponde exigir inspección diaria de
# Inicio/Fin (si no trabajó ese día, no aplica -> "N/A").
FAENAS_FORM_IDS = [522460, 704423]


def fetch_form_answers(form_id: int, start: str | None = None, end: str | None = None) -> list[dict]:
    """Trae las respuestas (submissions) de un formulario dado.

    `start`/`end` (formato "YYYY-MM-DD") filtran por fecha de envío del
    formulario en Datascope. Si no se pasan, se usa una ventana amplia
    (DEFAULT_LOOKBACK_DAYS) para no perder registros por la ventana corta
    por defecto de la API.

    Cada elemento tiene: form_answer_id, form_id, form_name, user_name,
    created_at, updated_at, finished, y una lista "answers" con las
    respuestas a cada pregunta del formulario.
    """
    if start is None:
        start = (date.today() - timedelta(days=DEFAULT_LOOKBACK_DAYS)).isoformat()
    if end is None:
        end = date.today().isoformat()

    resp = requests.get(
        f"{BASE_URL}/answers",
        headers={"Authorization": config.DATASCOPE_API_KEY},
        params={"form_id": form_id, "start": start, "end": end},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json() or []


def _get_answer_value(submission: dict, question_name: str):
    """Busca el valor de una pregunta por nombre dentro de una submission.
    Si la pregunta se repite (multi-select), devuelve una lista de valores.
    """
    values = [
        a.get("question_value")
        for a in submission.get("answers", [])
        if a.get("question_name") == question_name
    ]
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return values


def _extract_patente(submission: dict) -> str | None:
    """El campo "Patente" viene como "TWRD42 | CM42" (patente | código
    interno de Datascope) -- nos quedamos solo con la patente.
    """
    patente_raw = _get_answer_value(submission, "Patente") or ""
    return patente_raw.split("|")[0].strip() if patente_raw else None


def normalize_submission(submission: dict) -> dict:
    """Convierte una submission cruda de Datascope en un registro plano,
    listo para guardar en la tabla `mantenimiento_registros`.
    """
    patente = _extract_patente(submission)

    sistemas = _get_answer_value(submission, "Sistemas Trabajados")
    if sistemas is not None and not isinstance(sistemas, list):
        sistemas = [sistemas]

    trabajos_texto = [
        a.get("question_value")
        for a in submission.get("answers", [])
        if a.get("question_name") == "Trabajos Realizados"
        and a.get("question_type") == "text"
    ]

    fotos = [
        a.get("question_value")
        for a in submission.get("answers", [])
        if a.get("question_type") == "photo"
    ]

    return {
        "form_answer_id": submission.get("form_answer_id"),
        "form_id": submission.get("form_id"),
        "patente": patente,
        "tipo_mantenimiento": _get_answer_value(submission, "Tipo de Mantenimiento"),
        "fecha_inicio": _get_answer_value(submission, "Fecha Inicio Trabajos"),
        "fecha_fin": _get_answer_value(submission, "Fecha Fin Trabajos"),
        "usuario": submission.get("user_name"),
        "sistemas_trabajados": ", ".join(sistemas) if sistemas else None,
        "trabajos_realizados": " | ".join(t for t in trabajos_texto if t) or None,
        "fotos": ", ".join(fotos) if fotos else None,
        "finished": submission.get("finished"),
        "created_at": submission.get("created_at"),
        "updated_at": submission.get("updated_at"),
    }


def fetch_normalized_registros(
    form_id: int | None = None, start: str | None = None, end: str | None = None
) -> list[dict]:
    """Trae y normaliza todas las submissions del formulario de mantenimiento."""
    form_id = form_id or config.DATASCOPE_FORM_ID
    raw = fetch_form_answers(form_id, start=start, end=end)
    return [normalize_submission(s) for s in raw]


def normalize_faena(submission: dict) -> dict:
    """Convierte una submission de "Reporte Faenas en Terreno" en un
    registro plano, listo para guardar en la tabla `faenas_registros`.
    """
    return {
        "form_answer_id": submission.get("form_answer_id"),
        "form_id": submission.get("form_id"),
        "patente": _extract_patente(submission),
        "fecha_reporte": _get_answer_value(submission, "Fecha de Reporte"),
        "created_at": submission.get("created_at"),
    }


def fetch_normalized_faenas(start: str | None = None, end: str | None = None) -> list[dict]:
    """Trae y normaliza las submissions de ambos formularios de Reporte de
    Faenas en Terreno (indican si el camión salió a trabajar ese día).
    """
    resultado = []
    for form_id in FAENAS_FORM_IDS:
        raw = fetch_form_answers(form_id, start=start, end=end)
        resultado.extend(normalize_faena(s) for s in raw)
    return resultado
