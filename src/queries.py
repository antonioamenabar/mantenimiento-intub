"""Consultas de negocio para el cuadrante de Inspecciones:
cumplimiento diario (inicio/fin de jornada) y semanal, por camión.
"""
import json
from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import select

from src.db import mantenimiento_registros, faenas_registros, tickets, fallas_historico, flota

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


def _primera_foto(fotos_str):
    # pd.isna(), no `if not fotos_str:` a secas: una columna de la base con
    # NULL mezclado con texto real llega acá como NaN (float) vía pandas,
    # y "not NaN" da False (NaN no es falsy) -- .split() sobre un float
    # revienta con AttributeError.
    if pd.isna(fotos_str) or not fotos_str:
        return None
    return fotos_str.split(", ")[0]


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


def _load_flota(engine, patentes: list[str] | None = None) -> pd.DataFrame:
    """Carga el maestro de flota. Por defecto solo los camiones activos;
    si se pasa `patentes`, carga exactamente esas (sin filtrar por activo --
    así el filtro de patentes puede traer de vuelta camiones excluidos por
    defecto, como SPSC56/TSSZ75).
    """
    stmt = select(flota)
    if patentes is not None:
        stmt = stmt.where(flota.c.patente.in_(patentes))
    else:
        stmt = stmt.where(flota.c.activo.is_(True))
    stmt = stmt.order_by(flota.c.orden)
    with engine.connect() as conn:
        return pd.read_sql(stmt, conn)


def opciones_patentes(engine) -> pd.DataFrame:
    """Todas las patentes disponibles para el filtro (activas + excluidas
    por defecto), ordenadas igual que en la tabla.
    """
    stmt = select(flota).order_by(flota.c.orden)
    with engine.connect() as conn:
        return pd.read_sql(stmt, conn)


def _set_trabajo(engine, lunes, domingo) -> set:
    """Set de (patente, fecha) para los que hay Reporte de Faenas en
    Terreno (indica que el camión salió a trabajar ese día) en el rango
    [lunes, domingo]. Se usa un set en vez de filtrar un DataFrame para no
    repetir el bug de pandas de perder columnas al filtrar vacíos.
    """
    stmt = select(faenas_registros)
    with engine.connect() as conn:
        df = pd.read_sql(stmt, conn)
    resultado = set()
    for _, r in df.iterrows():
        d = _parse_fecha(r["fecha_reporte"])
        if d is not None and lunes <= d.date() <= domingo:
            resultado.add((r["patente"], d.date()))
    return resultado


DIAS_SEMANA = ["Lun", "Mar", "Mié", "Jue", "Vie"]  # checklist diario solo aplica de lunes a viernes

# --- Verificación manual de fotos (revisión visual hecha el 20-08-2026) ---
# Se revisaron 31 fotos de la semana 17-08 al 20-08: las 15 de "Inspección
# Diaria Fin" casi todas corresponden al formulario de papel correcto (con
# patente y fecha coincidentes), salvo 1 excepción listada abajo. En cambio,
# de las 16 de "Inspección Diaria Inicio" -- revisando la foto principal de
# las 16 y el set completo de fotos de 3 de ellas (25 fotos en total) -- NINGUNA
# corresponde al formulario de papel de Inicio de Faena: todas son fotos de
# evidencia mecánica (correa, refrigerante, aceite, neumáticos, patente del
# camión), no el checklist escaneado. Por eso, mientras no se confirme lo
# contrario, los "Inicio" se muestran como "?" en vez de "✅".
#
# OJO: esto es una revisión manual puntual, no una verificación automática.
# Si se agregan más semanas de datos hay que repetir la revisión a mano, o
# automatizarla integrando una llamada a un modelo de visión en la
# sincronización (no está hecho todavía).
FOTO_INICIO_NO_VERIFICABLE = True

FOTO_EXCEPCIONES_MISMATCH = {
    # (patente, tipo_mantenimiento, "dd-mm-YYYY"): motivo (documentado, no usado en código)
    ("TDKR30", "Inspección Diaria Fin", "20-08-2026"): "foto repetida de un reporte del 10-08-2026",
}


def opciones_semana(hoy: datetime | None = None, n_semanas: int = 10) -> list[tuple]:
    """Lista de (lunes, etiqueta) para las últimas `n_semanas`, de la más
    reciente (semana actual) a la más antigua. Para usar en un selector.
    """
    hoy = hoy or datetime.now()
    lunes_actual = (hoy - timedelta(days=hoy.weekday())).date()
    opciones = []
    for i in range(n_semanas):
        lunes = lunes_actual - timedelta(weeks=i)
        domingo = lunes + timedelta(days=6)
        etiqueta = f"{lunes.strftime('%d-%m')} al {domingo.strftime('%d-%m')}"
        if i == 0:
            etiqueta += " (semana actual)"
        opciones.append((lunes, etiqueta))
    return opciones


def matriz_cumplimiento_diario(
    engine, semana_inicio=None, hoy: datetime | None = None, patentes: list[str] | None = None
) -> pd.DataFrame:
    """Matriz camión x día: una fila por camión, dos columnas por día de la
    semana (lunes a viernes) -- "{Día} Inicio" y "{Día} Fin", más una columna
    de foto por cada una ("{Día} Inicio_foto") y el % de cumplimiento total.

    El valor de cada checklist es:
    - None si el día todavía no ha ocurrido (no aplica).
    - "N/A" si el camión no registra Reporte de Faenas en Terreno ese día
      (no salió a trabajar, así que no corresponde exigirle inspección).
    - True/False según si se hizo ese checklist puntual ese día.

    `pct_cumplimiento` = realizados / esperados (solo días donde el camión
    trabajó y ya ocurrieron) -- None si no le correspondía ninguno todavía.
    """
    hoy = hoy or datetime.now()
    lunes = semana_inicio or (hoy - timedelta(days=hoy.weekday())).date()
    if hasattr(lunes, "date"):
        lunes = lunes.date()
    dias = [lunes + timedelta(days=i) for i in range(7)]
    hoy_date = hoy.date()

    flota_df = _load_flota(engine, patentes)
    registros = _load_registros(engine, [TIPO_INICIO, TIPO_FIN])
    if not registros.empty:
        registros = registros[registros["fecha_inicio_dt"].apply(
            lambda d: d is not None and lunes <= d.date() <= dias[-1]
        )]
    trabajo_set = _set_trabajo(engine, lunes, dias[-1])

    filas = []
    for _, camion in flota_df.iterrows():
        fila = {"patente": camion["patente"], "alias": camion["alias"], "nombre_corto": camion["nombre_corto"]}
        del_camion = registros[registros["patente"] == camion["patente"]]
        realizados = 0
        esperados = 0
        for dia, etiqueta in zip(dias, DIAS_SEMANA):
            col_inicio, col_fin = f"{etiqueta} Inicio", f"{etiqueta} Fin"
            foto_inicio, foto_fin = f"{col_inicio}_foto", f"{col_fin}_foto"
            if dia > hoy_date:
                fila[col_inicio] = None  # día futuro, no aplica todavía
                fila[col_fin] = None
                fila[foto_inicio] = None
                fila[foto_fin] = None
                continue
            if (camion["patente"], dia) not in trabajo_set:
                fila[col_inicio] = "N/A"  # no trabajó ese día
                fila[col_fin] = "N/A"
                fila[foto_inicio] = None
                fila[foto_fin] = None
                continue
            esperados += 2
            if del_camion.empty:
                fila[col_inicio] = False
                fila[col_fin] = False
                fila[foto_inicio] = None
                fila[foto_fin] = None
                continue
            del_dia = del_camion[del_camion["fecha_inicio_dt"].apply(lambda d: d.date() == dia)]
            reg_inicio = del_dia[del_dia["tipo_mantenimiento"] == TIPO_INICIO]
            reg_fin = del_dia[del_dia["tipo_mantenimiento"] == TIPO_FIN]
            tiene_inicio, tiene_fin = not reg_inicio.empty, not reg_fin.empty
            fecha_str = dia.strftime("%d-%m-%Y")
            # El checklist SÍ se hizo (cuenta para el % de cumplimiento);
            # "?" solo indica que la foto adjunta no se pudo verificar.
            fila[col_inicio] = "?" if tiene_inicio and FOTO_INICIO_NO_VERIFICABLE else tiene_inicio
            if tiene_fin and (camion["patente"], TIPO_FIN, fecha_str) in FOTO_EXCEPCIONES_MISMATCH:
                fila[col_fin] = "?"
            else:
                fila[col_fin] = tiene_fin
            fila[foto_inicio] = _primera_foto(reg_inicio.iloc[0]["fotos"]) if tiene_inicio else None
            fila[foto_fin] = _primera_foto(reg_fin.iloc[0]["fotos"]) if tiene_fin else None
            realizados += int(tiene_inicio) + int(tiene_fin)
        fila["realizados"] = realizados
        fila["esperados"] = esperados
        fila["pct_cumplimiento"] = (realizados / esperados * 100) if esperados else None
        filas.append(fila)
    return pd.DataFrame(filas)


def semanal_ultimas_semanas_cerradas(
    engine, n_semanas: int = 2, semana_referencia=None, hoy: datetime | None = None,
    patentes: list[str] | None = None,
) -> pd.DataFrame:
    """Para cada camión: ¿se hizo la Inspección Semanal en alguna de las
    `n_semanas` semanas CERRADAS anteriores a `semana_referencia` (lunes a
    domingo ya terminadas, sin contar esa semana). Por defecto,
    `semana_referencia` es la semana actual real (hoy).
    """
    hoy = hoy or datetime.now()
    lunes_semana_actual = semana_referencia or (hoy - timedelta(days=hoy.weekday())).date()
    fin_ventana = lunes_semana_actual - timedelta(days=1)  # domingo anterior
    inicio_ventana = lunes_semana_actual - timedelta(days=7 * n_semanas)

    flota_df = _load_flota(engine, patentes)
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
            "inspeccion_semanal_2_sem": cumplida,
        })
    return pd.DataFrame(resultado)


# --- Cuadrante de Fallas (Tickets de Datascope, menú "Tickets" / API "findings") ---

PRIORIDADES = ["critical", "high", "medium", "low"]
PRIORIDAD_LABEL = {"critical": "Crítica", "high": "Alta", "medium": "Media", "low": "Baja"}

ANTIGUEDAD_BUCKETS = ["Menos de 7 días", "Entre 8 y 21 días", "Más de 21 días"]
# Claves cortas, sin tildes ni espacios, para armar los query params del link
# clickeable de cada celda (patente/prioridad/antigüedad no deberían tener
# caracteres raros en una URL).
ANTIGUEDAD_KEY = {"Menos de 7 días": "menos7", "Entre 8 y 21 días": "8-21", "Más de 21 días": "mas21"}
ANTIGUEDAD_KEY_INV = {v: k for k, v in ANTIGUEDAD_KEY.items()}


def _dias_antiguedad(creation_date_str, hoy: datetime | None = None):
    hoy = hoy or datetime.now()
    if not creation_date_str:
        return None
    try:
        fecha = datetime.strptime(creation_date_str, "%d/%m/%Y %H:%M")
    except ValueError:
        return None
    return (hoy - fecha).days


def _bucket_antiguedad(dias) -> str | None:
    if dias is None:
        return None
    if dias < 7:
        return "Menos de 7 días"
    if dias <= 21:
        return "Entre 8 y 21 días"
    return "Más de 21 días"


def _col_cruzada(prioridad_label: str, bucket: str) -> str:
    """Nombre de columna para el cruce prioridad x antigüedad, ej.
    'Crítica||Menos de 7 días'."""
    return f"{prioridad_label}||{bucket}"


def _load_tickets(engine) -> pd.DataFrame:
    stmt = select(tickets)
    with engine.connect() as conn:
        df = pd.read_sql(stmt, conn)
    if df.empty:
        columnas = [c.name for c in tickets.columns]
        return pd.DataFrame(columns=columnas)
    return df


def matriz_fallas(engine, patentes: list[str] | None = None) -> pd.DataFrame:
    """Matriz camión x (prioridad x antigüedad): una fila por camión, y para
    cada prioridad (Crítica, Alta, Media, Baja, en ese orden) tres columnas
    con la cantidad de tickets según antigüedad (Menos de 7 días / Entre 8 y
    21 días / Más de 21 días), más una columna final con el total.
    """
    flota_df = _load_flota(engine, patentes)
    tickets_df = _load_tickets(engine)

    filas = []
    for _, camion in flota_df.iterrows():
        del_camion = tickets_df[tickets_df["patente"] == camion["patente"]] if not tickets_df.empty else tickets_df
        fila = {"patente": camion["patente"], "alias": camion["alias"], "nombre_corto": camion["nombre_corto"]}
        if not del_camion.empty:
            buckets = del_camion["creation_date"].apply(lambda d: _bucket_antiguedad(_dias_antiguedad(d)))
        else:
            buckets = pd.Series(dtype="object")
        total = 0
        for p in PRIORIDADES:
            label = PRIORIDAD_LABEL[p]
            es_prioridad = (del_camion["priority"] == p) if not del_camion.empty else pd.Series(dtype="bool")
            for b in ANTIGUEDAD_BUCKETS:
                n = int((es_prioridad & (buckets == b)).sum()) if not del_camion.empty else 0
                fila[_col_cruzada(label, b)] = n
                total += n
        fila["Total"] = total
        filas.append(fila)
    return pd.DataFrame(filas)


def fila_fallas_a_json(fila: dict) -> str:
    """Serializa las columnas de conteo (cruce prioridad x antigüedad + Total)
    de una fila de matriz_fallas() para guardar en fallas_historico.datos_json.
    """
    cols = [_col_cruzada(PRIORIDAD_LABEL[p], b) for p in PRIORIDADES for b in ANTIGUEDAD_BUCKETS] + ["Total"]
    return json.dumps({c: int(fila[c]) for c in cols}, ensure_ascii=False)


def _load_fallas_historico(engine, semana_inicio) -> pd.DataFrame:
    stmt = select(fallas_historico).where(fallas_historico.c.semana_inicio == semana_inicio.strftime("%Y-%m-%d"))
    with engine.connect() as conn:
        df = pd.read_sql(stmt, conn)
    if df.empty:
        return df
    datos = df["datos_json"].apply(json.loads).apply(pd.Series)
    return pd.concat([df[["patente", "nombre_corto"]], datos], axis=1)


def matriz_fallas_semana(
    engine, semana_inicio, patentes: list[str] | None = None, hoy: datetime | None = None,
) -> tuple[pd.DataFrame, bool]:
    """Igual que matriz_fallas(), pero para una semana elegida (como en
    Inspecciones). Si `semana_inicio` es la semana actual, se calcula en
    vivo (estado de ahora mismo). Si es una semana pasada, se busca la foto
    guardada por `snapshot_fallas.py` -- devuelve DataFrame vacío si esa
    semana todavía no tiene foto guardada.

    Devuelve (tabla, es_en_vivo).
    """
    hoy = hoy or datetime.now()
    lunes_actual = (hoy - timedelta(days=hoy.weekday())).date()
    if hasattr(semana_inicio, "date"):
        semana_inicio = semana_inicio.date() if not isinstance(semana_inicio, type(lunes_actual)) else semana_inicio

    if semana_inicio >= lunes_actual:
        return matriz_fallas(engine, patentes=patentes), True

    df = _load_fallas_historico(engine, semana_inicio)
    if patentes is not None and not df.empty:
        df = df[df["patente"].isin(patentes)]
        orden = {p: i for i, p in enumerate(patentes)}
        df = df.sort_values(by="patente", key=lambda s: s.map(orden)).reset_index(drop=True)
    return df, False


def detalle_fallas(engine, patente: str, prioridad_key: str, bucket: str) -> pd.DataFrame:
    """Lista de tickets (Descripción, Fecha creación) para una celda puntual
    de la matriz (un camión, una prioridad, un rango de antigüedad). Solo
    tiene sentido para la semana EN VIVO -- el histórico no guarda el
    detalle ticket a ticket, solo los conteos.
    """
    tickets_df = _load_tickets(engine)
    if tickets_df.empty:
        return pd.DataFrame(columns=["Descripción", "Fecha creación"])
    del_camion = tickets_df[
        (tickets_df["patente"] == patente) & (tickets_df["priority"] == prioridad_key)
    ]
    if del_camion.empty:
        return pd.DataFrame(columns=["Descripción", "Fecha creación"])
    buckets = del_camion["creation_date"].apply(lambda d: _bucket_antiguedad(_dias_antiguedad(d)))
    del_bucket = del_camion[buckets == bucket]
    if del_bucket.empty:
        return pd.DataFrame(columns=["Descripción", "Fecha creación"])
    resultado = del_bucket.apply(
        lambda r: pd.Series({
            "Descripción": (r["description"] or r["name"] or "").strip() or "(sin descripción)",
            "Fecha creación": r["creation_date"],
        }),
        axis=1,
    )
    return resultado.reset_index(drop=True)


def fallas_nuevas_desde(engine, desde: datetime | None) -> pd.DataFrame:
    """Tickets (no cerrados) creados después de `desde` -- para el aviso de
    "fallas nuevas desde tu última visita" del Dashboard. `desde=None`
    (usuario que nunca ha entrado) no muestra nada -- no tiene sentido
    avisar de "todo lo que existe" la primera vez que alguien entra.
    """
    if desde is None:
        return pd.DataFrame(columns=["patente", "priority", "creation_date"])
    tickets_df = _load_tickets(engine)
    if tickets_df.empty:
        return tickets_df
    fechas = tickets_df["creation_date"].apply(
        lambda d: datetime.strptime(d, "%d/%m/%Y %H:%M") if d and pd.notna(d) else None
    )
    return tickets_df[fechas.apply(lambda f: f is not None and f > desde)].reset_index(drop=True)
