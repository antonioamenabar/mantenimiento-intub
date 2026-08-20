"""Cliente para la API de Datascope.

Documentación oficial: https://dscope.github.io/docs/
Ojo: existe también "DataScope Select" de LSEG/Refinitiv, que es un producto
financiero totalmente distinto — no confundir la documentación.
"""
import requests

from src import config

BASE_URL = "https://www.mydatascope.com/api/external"


def fetch_form_answers(form_id: int) -> list[dict]:
    """Trae todas las respuestas (submissions) de un formulario dado.

    Cada elemento tiene: form_answer_id, form_id, form_name, user_name,
    created_at, updated_at, finished, y una lista "answers" con las
    respuestas a cada pregunta del formulario.
    """
    resp = requests.get(
        f"{BASE_URL}/answers",
        headers={"Authorization": config.DATASCOPE_API_KEY},
        params={"form_id": form_id},
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


def normalize_submission(submission: dict) -> dict:
    """Convierte una submission cruda de Datascope en un registro plano,
    listo para guardar en la tabla `mantenimiento_registros`.
    """
    patente_raw = _get_answer_value(submission, "Patente") or ""
    # El valor viene como "TWRD42 | CM42" (patente | código interno)
    patente = patente_raw.split("|")[0].strip() if patente_raw else None

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


def fetch_normalized_registros(form_id: int | None = None) -> list[dict]:
    """Trae y normaliza todas las submissions del formulario de mantenimiento."""
    form_id = form_id or config.DATASCOPE_FORM_ID
    raw = fetch_form_answers(form_id)
    return [normalize_submission(s) for s in raw]
