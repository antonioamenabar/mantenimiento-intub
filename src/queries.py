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
    if df.empty:
        # pd.read_sql puede devolver un DataFrame sin columnas cuando no
        # hay filas -- forzamos el esquema esperado para que el resto del
        # código pueda seguir filtrando/accediendo columnas sin explotar.
        columnas = [c.name for c in mantenimiento_registros.columns] + ["fecha_inicio_dt"]
        return pd.DataFrame(columns=columnas)
    df["fecha_inicio_dt"] = df["fecha_inicio"].apply(_parse_fecha)
    return df


def _load_flota_activa(engine) -> pd.DataFrame:
    stmt = select(flota).where(flota.c.activo.is_(True))
    with engine.connect() as conn:
        return pd.read_sql(stmt, conn)


DIAS_SEMANA = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


def matriz_cumplimiento_diario(engine, semana_inicio=None, hoy: datetime | None = None) -> pd.DataFrame:
    """Matriz camión x día: una fila por camión, dos columnas por día de la
    semana (lunes a domingo) -- "{Día} Inicio" y "{Día} Fin". El valor es
    True/False según si se hizo ese checklist puntual ese día, y None si el
    día todavía no ha ocurrido (no aplica).
    """
    hoy = hoy or datetime.now()
    lunes = semana_inicio or (hoy - timedelta(days=hoy.weekday())).date()
    if hasattr(lunes, "date"):
        lunes = lunes.date()
    dias = [lunes + timedelta(days=i) for i in range(7)]
    hoy_date = hoy.date()

    flota_df = _load_flota_activa(engine)
    registros = _load_registros(engine, [TIPO_INICIO, TIPO_FIN])
    if not registros.empty:
        registros = registros[registros["fecha_inicio_dt"].apply(
            lambda d: d is not None and lunes <= d.date() <= dias[-1]
        )]

    filas = []
    for _, camion in flota_df.iterrows():
        fila = {"patente": camion["patente"], "alias": camion["alias"]}
        del_camion = registros[registros["patente"] == camion["patente"]]
        for dia, etiqueta in zip(dias, DIAS_SEMANA):
            col_inicio, col_fin = f"{etiqueta} Inicio", f"{etiqueta} Fin"
            if dia > hoy_date:
                fila[col_inicio] = None  # día futuro, no aplica todavía
                fila[col_fin] = None
                continue
            if del_camion.empty:
                fila[col_inicio] = False
                fila[col_fin] = False
                continue
            del_dia = del_camion[del_camion["fecha_inicio_dt"].apply(lambda d: d.date() == dia)]
            fila[col_inicio] = (del_dia["tipo_mantenimiento"] == TIPO_INICIO).any()
            fila[col_fin] = (del_dia["tipo_mantenimiento"] == TIPO_FIN).any()
        filas.append(fila)
    return pd.DataFrame(filas)


def semanal_ultimas_semanas_cerradas(engine, n_semanas: int = 2, hoy: datetime | None = None) -> pd.DataFrame:
    """Para cada camión activo: ¿se hizo la Inspección Semanal en alguna de
    las últimas `n_semanas` semanas CERRADAS (lunes a domingo ya terminadas,
    sin contar la semana actual en curso)?
    """
    hoy = hoy or datetime.now()
    lunes_semana_actual = (hoy - timedelta(days=hoy.weekday())).date()
    fin_ventana = lunes_semana_actual - timedelta(days=1)  # domingo anterior
    inicio_ventana = lunes_semana_actual - timedelta(days=7 * n_semanas)

    flota_df = _load_flota_activa(engine)
    registros = _load_registros(engine, [TIPO_SEMANAL])
    if not registros.empty:
        registros = registros[registros["fecha_inicio_dt"].apply(
            lambda d: d is not None and inicio_ventana <= d.date() <= fin_ventana
        )]

    resultado = []
    for _, camion in flota_df.iterrows():
        cumplida = (registros["patente"] == camion["patente"]).any()
        resultado.append({
            "patente": camion["patente"],
            "alias": camion["alias"],
            "inspeccion_semanal_2_sem": cumplida,
        })
    return pd.DataFrame(resultado)
