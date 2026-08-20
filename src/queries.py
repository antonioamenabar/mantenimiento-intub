"""Consultas de negocio para el cuadrante de Inspecciones:
cumplimiento diario (inicio/fin de jornada) y semanal, por camión.
"""
from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import select

from src.db import mantenimiento_registros, flota

FECHA_FORMATOS = ["%d-%m-%Y %H:%M", "%d-%m-%Y"]

TIPO_INICIO = "Inspección Diaria Inicio"
TIPO_FIN = "Inspección Diaria Fin"
TIPO_SEMANAL = "Inspección Semanal"


def _parse_fecha(valor):
    if not valor:
        return None
    for fmt in FECHA_FORMATOS:
        try:
            return datetime.strptime(valor, fmt)
        except ValueError:
            continue
    return None


def _load_registros(engine, tipos: list[str]) -> pd.DataFrame:
    stmt = select(mantenimiento_registros).where(
        mantenimiento_registros.c.tipo_mantenimiento.in_(tipos)
    )
    with engine.connect() as conn:
        df = pd.read_sql(stmt, conn)
    if not df.empty:
        df["fecha_inicio_dt"] = df["fecha_inicio"].apply(_parse_fecha)
    return df


def _load_flota_activa(engine) -> pd.DataFrame:
    stmt = select(flota).where(flota.c.activo.is_(True))
    with engine.connect() as conn:
        return pd.read_sql(stmt, conn)


def cumplimiento_diario(engine, fecha: datetime | None = None) -> pd.DataFrame:
    """Para cada camión activo: ¿tiene inspección de Inicio y de Fin de
    jornada en la fecha dada (por defecto, hoy)?
    """
    fecha = fecha or datetime.now()
    dia = fecha.date()

    flota_df = _load_flota_activa(engine)
    registros = _load_registros(engine, [TIPO_INICIO, TIPO_FIN])

    if not registros.empty:
        registros = registros[registros["fecha_inicio_dt"].apply(
            lambda d: d is not None and d.date() == dia
        )]

    resultado = []
    for _, camion in flota_df.iterrows():
        del_camion = registros[registros["patente"] == camion["patente"]]
        tiene_inicio = (del_camion["tipo_mantenimiento"] == TIPO_INICIO).any()
        tiene_fin = (del_camion["tipo_mantenimiento"] == TIPO_FIN).any()
        resultado.append({
            "patente": camion["patente"],
            "alias": camion["alias"],
            "inspeccion_inicio": tiene_inicio,
            "inspeccion_fin": tiene_fin,
            "completo": tiene_inicio and tiene_fin,
        })
    return pd.DataFrame(resultado)


def cumplimiento_semanal(engine, hoy: datetime | None = None) -> pd.DataFrame:
    """Para cada camión activo: estado de la inspección semanal detallada
    en la semana actual (lunes a domingo) -> hecha / pendiente / vencida.
    "vencida" solo aplica si ya es domingo y no se ha hecho.
    """
    hoy = hoy or datetime.now()
    lunes = (hoy - timedelta(days=hoy.weekday())).date()
    es_domingo = hoy.weekday() == 6

    flota_df = _load_flota_activa(engine)
    registros = _load_registros(engine, [TIPO_SEMANAL])

    if not registros.empty:
        registros = registros[registros["fecha_inicio_dt"].apply(
            lambda d: d is not None and d.date() >= lunes
        )]

    resultado = []
    for _, camion in flota_df.iterrows():
        hecha = (registros["patente"] == camion["patente"]).any()
        if hecha:
            estado = "hecha"
        elif es_domingo:
            estado = "vencida"
        else:
            estado = "pendiente"
        resultado.append({
            "patente": camion["patente"],
            "alias": camion["alias"],
            "estado": estado,
        })
    return pd.DataFrame(resultado)
