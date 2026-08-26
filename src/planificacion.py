"""Mantenimiento Programado: catálogo de componentes mayores, reglas de
intervalo por marca/modelo, componente físico instalado por camión, y
registro de mantenciones realizadas -- alimenta la matriz del 3er cuadrante
del dashboard.

Diseño en 3 capas (ver conversación con Antonio, 24-08-2026):
  1. `item_catalogo` + `reglas_mantencion`: qué se puede registrar y cada
     cuánto corresponde, según lo investigado (manuales de fábrica donde los
     hay, práctica de industria donde no).
  2. `componentes_camion`: qué marca/modelo tiene instalado cada camión --
     se llena con las placas de bomba de agua, bomba de vacío y PTO. Mientras
     no haya fila, se usa la regla genérica del ítem (marca=NULL).
  3. `eventos_mantenimiento`: el registro real de trabajos hechos --
     alimentado por el formulario "Registrar mantención" del dashboard.

La matriz del dashboard (`matriz_mantenimiento`) cruza las 3 capas: para
cada (patente, item) busca el último evento, la regla que corresponde según
el componente instalado (o la genérica si no se conoce), y calcula el
estado de vencimiento.
"""
from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import select

from src.db import (
    item_catalogo, reglas_mantencion, componentes_camion,
    eventos_mantenimiento,
    upsert_item_catalogo, replace_reglas_mantencion, upsert_componentes_camion,
    insertar_eventos_mantenimiento,
)
from src.queries import _load_flota

# ---------------------------------------------------------------------------
# Capa 1: catálogo y reglas (constantes en Python -- fuente única de verdad;
# `seed_catalogo_y_reglas` las vuelca a la base cada vez que corre la app).
# ---------------------------------------------------------------------------

CATEGORIA_LABEL = {"camion": "Camión", "equipo": "Equipo"}
CONFIANZA_LABEL = {"confirmado": "Confirmado", "estimado": "Estimado", "sindato": "Sin dato"}
CONFIANZA_BADGE = {"confirmado": "🟢", "estimado": "🟡", "sindato": "🔴"}

# (item_key, categoria, nombre, orden)
ITEMS = [
    ("motor_aceite", "camion", "Aceite motor", 1),
    ("filtro_combustible", "camion", "Filtro combustible", 2),
    ("filtro_aire", "camion", "Filtro aire", 3),
    ("frenos", "camion", "Frenos", 4),
    ("neumaticos", "camion", "Neumáticos", 5),
    ("caja_cambios", "camion", "Caja de cambios", 6),
    ("diferencial", "camion", "Diferencial", 7),
    ("suspension", "camion", "Suspensión", 8),
    ("bomba_agua", "equipo", "Bomba de agua", 9),
    ("bomba_vacio", "equipo", "Bomba de vacío", 10),
    ("pto", "equipo", "PTO", 11),
    ("crucetas_cardanes", "equipo", "Crucetas / cardanes", 12),
    ("hidraulico_equipo", "equipo", "Hidráulico equipo", 13),
    ("neumatico_equipo", "equipo", "Neumático equipo", 14),
]

# (item_key, marca, modelo, intervalo_meses, intervalo_horas, intervalo_km, confianza, fuente)
# marca/modelo en None = regla genérica para ese item_key. `intervalo_km`
# queda en None para todo -- la flota se trackea por horómetro, no por
# odómetro; se completa el día que algún camión empiece a registrarse por
# kilometraje.
REGLAS = [
    # --- Camión (chasis): mismo ciclo estándar de industria para todos ---
    ("motor_aceite", None, None, 3, 500, None, "estimado", "Práctica estándar de industria (chasis diésel pesado)"),
    ("filtro_combustible", None, None, 3, 500, None, "estimado", "Práctica estándar de industria"),
    ("filtro_aire", None, None, 3, 500, None, "estimado", "Práctica estándar de industria"),
    ("frenos", None, None, 3, 500, None, "estimado", "Práctica estándar de industria"),
    ("neumaticos", None, None, 3, 500, None, "estimado", "Práctica estándar de industria"),
    ("caja_cambios", None, None, 12, None, None, "estimado", "Práctica estándar de industria"),
    ("diferencial", None, None, 12, None, None, "estimado", "Práctica estándar de industria"),
    ("suspension", None, None, 12, None, None, "estimado", "Práctica estándar de industria"),

    # --- Equipo: genéricos (fallback cuando no se conoce el componente) ---
    ("bomba_agua", None, None, 6, 1000, None, "sindato", "Sin marca conocida -- ciclo genérico de Equipo"),
    ("bomba_vacio", None, None, 6, 1000, None, "sindato", "Sin marca conocida -- ciclo genérico de Equipo"),
    ("pto", None, None, 6, 1000, None, "sindato", "Sin dato de marca ni intervalo -- pendiente placa"),
    ("crucetas_cardanes", None, None, 1, None, None, "estimado", "Práctica general de engrase en camiones pesados"),
    ("hidraulico_equipo", None, None, 6, 1000, None, "sindato", "Sin dato de marca ni intervalo"),
    ("neumatico_equipo", None, None, 6, 1000, None, "sindato", "Sin dato de marca ni intervalo"),

    # --- Equipo: confirmadas/estimadas por marca (investigación Programa de Mantenimiento) ---
    ("bomba_agua", "Meyers", "DP-80", 3, 300, None, "confirmado", "Manual serie DP Meyers/Pentair (cambio de aceite 300 h)"),
    ("bomba_vacio", "Roots", "824", 6, 2000, None, "confirmado", "Manual Roots 824 RCS -- aceite mineral, ~2.000 h a 82°C"),
    ("bomba_agua", "Pratissoli", None, 6, 1000, None, "confirmado", "Manual oficial Pratissoli (serie KS: 1.000 h)"),
    ("bomba_vacio", "Kaeser", "Omega 53P", 6, None, None, "confirmado", "Manual Kaeser Omega 53P -- cambio semestral"),
    ("crucetas_cardanes", "Kaeser", None, 1, 40, None, "confirmado", "Manual Kaeser Omega 53P -- engrase crucetas PTO"),
    ("bomba_agua", "Uraca", "KD716G", 6, 500, None, "estimado", "Sin manual oficial -- vida útil típica bombas plunger"),
    ("bomba_vacio", "Wittig", "RFW 200", 6, 400, None, "estimado", "Folleto Wittig no especifica intervalo de cambio"),
    ("bomba_vacio", "Vactor", None, 3, 250, None, "estimado", "Soplador tipo Roots/Hibon -- práctica de industria"),
    ("hidraulico_equipo", "Vactor", None, 6, 500, None, "estimado", "Práctica de industria para hidráulico de equipo Vactor"),
]


def seed_catalogo_y_reglas(engine):
    """Vuelca las constantes ITEMS/REGLAS a la base. Idempotente -- se puede
    llamar cada vez que arranca el dashboard sin duplicar nada.
    """
    upsert_item_catalogo(engine, [
        {"item_key": k, "categoria": cat, "nombre": nombre, "orden": orden}
        for k, cat, nombre, orden in ITEMS
    ])
    replace_reglas_mantencion(engine, [
        {
            "item_key": item_key, "marca": marca, "modelo": modelo,
            "intervalo_meses": meses, "intervalo_horas": horas, "intervalo_km": km,
            "confianza": confianza, "fuente": fuente,
        }
        for item_key, marca, modelo, meses, horas, km, confianza, fuente in REGLAS
    ])


# ---------------------------------------------------------------------------
# Capa 2: componentes físicos conocidos por camión (lo que ya investigamos
# en el Programa de Mantenimiento -- se completa con las placas que faltan).
# ---------------------------------------------------------------------------

# (patente, item_key, marca, modelo, tiene_horometro_propio)
COMPONENTES_CONOCIDOS = [
    ("RDPT96", "bomba_agua", "Meyers", "DP-80", None),
    ("RDPT96", "bomba_vacio", "Roots", "824", None),
    ("TBGD22", "bomba_agua", "Meyers", "DP-80", None),
    ("TBGD22", "bomba_vacio", "Roots", "824", None),
    ("TDKR30", "bomba_agua", "Uraca", "KD716G", None),
    ("TDKR30", "bomba_vacio", "Wittig", "RFW 200", None),
    ("TDLR57", "bomba_agua", "Uraca", "KD716G", None),
    ("TDLR57", "bomba_vacio", "Wittig", "RFW 200", None),
    ("VGRJ98", "bomba_agua", "Uraca", "KD716G", None),
    ("VGRJ98", "bomba_vacio", "Wittig", "RFW 200", None),
    ("TWRD48", "bomba_agua", "Pratissoli", None, None),
    ("TWRD48", "bomba_vacio", "Kaeser", "Omega 53P", None),
    ("TWRD48", "crucetas_cardanes", "Kaeser", None, None),
    ("VFJH22", "bomba_agua", "Pratissoli", None, None),
    ("VFJH22", "bomba_vacio", "Kaeser", "Omega 53P", None),
    ("VFJH22", "crucetas_cardanes", "Kaeser", None, None),
    ("HLYR85", "bomba_agua", "Vactor", None, None),
    ("HLYR85", "bomba_vacio", "Vactor", None, None),
    ("HLYR85", "hidraulico_equipo", "Vactor", None, None),
    # VHSJ59 (Camel 5) sí mostró horómetro propio de soplador/bomba en su
    # factura de compra -- se deja marcado aunque todavía no sepamos la
    # marca, para que la matriz sepa que ahí conviene pedir la lectura de
    # horómetro en vez de solo la fecha.
    ("VHSJ59", "bomba_agua", None, None, True),
    ("VHSJ59", "bomba_vacio", None, None, True),
]


def seed_componentes_conocidos(engine):
    """Carga lo que ya sabemos de marca/modelo por camión (investigación del
    Programa de Mantenimiento). Usa upsert -- si se llama después de que
    alguien corrigió un componente a mano en el dashboard, esta lista fija
    le pasaría por encima. Por eso `seed_componentes_conocidos_si_vacio` es
    la que se llama automáticamente al arrancar la app; esta función queda
    para un re-seed deliberado (ej. al resetear la base de desarrollo).
    """
    upsert_componentes_camion(engine, [
        {
            "patente": patente, "item_key": item_key, "marca": marca, "modelo": modelo,
            "numero_serie": None, "tiene_horometro_propio": bool(horometro),
        }
        for patente, item_key, marca, modelo, horometro in COMPONENTES_CONOCIDOS
    ])


def seed_componentes_conocidos_si_vacio(engine):
    """Igual que `seed_componentes_conocidos`, pero solo si la tabla está
    vacía -- así el arranque normal del dashboard nunca pisa una corrección
    manual (ej. cuando llegue la placa real de un Camel 1200 y alguien
    corrija el componente desde el dashboard).
    """
    with engine.connect() as conn:
        total = conn.execute(select(componentes_camion)).fetchone()
    if total is None:
        seed_componentes_conocidos(engine)


def guardar_componente(engine, patente, item_key, marca, modelo, numero_serie, tiene_horometro_propio):
    """Registra (o corrige) el componente físico instalado -- lo que se
    completa cuando llega la placa de un camión.
    """
    upsert_componentes_camion(engine, [{
        "patente": patente, "item_key": item_key, "marca": marca or None, "modelo": modelo or None,
        "numero_serie": numero_serie or None, "tiene_horometro_propio": bool(tiene_horometro_propio),
    }])


# ---------------------------------------------------------------------------
# Consultas de catálogo / componentes
# ---------------------------------------------------------------------------

def catalogo_items(engine) -> pd.DataFrame:
    with engine.connect() as conn:
        df = pd.read_sql(select(item_catalogo).order_by(item_catalogo.c.orden), conn)
    if df.empty:
        return pd.DataFrame(columns=["item_key", "categoria", "nombre", "orden"])
    return df


def _cargar_reglas(engine) -> pd.DataFrame:
    with engine.connect() as conn:
        df = pd.read_sql(select(reglas_mantencion), conn)
    if df.empty:
        return pd.DataFrame(columns=[
            "id", "item_key", "marca", "modelo", "intervalo_meses",
            "intervalo_horas", "intervalo_km", "confianza", "fuente",
        ])
    return df


def _cargar_componentes(engine, patentes: list[str] | None = None) -> pd.DataFrame:
    stmt = select(componentes_camion)
    if patentes is not None:
        stmt = stmt.where(componentes_camion.c.patente.in_(patentes))
    with engine.connect() as conn:
        df = pd.read_sql(stmt, conn)
    if df.empty:
        return pd.DataFrame(columns=[
            "patente", "item_key", "marca", "modelo", "numero_serie", "tiene_horometro_propio",
        ])
    return df


def componentes_instalados(engine, patente: str | None = None) -> pd.DataFrame:
    """Vista de "qué componente tiene cada camión" para mostrar/editar en el
    dashboard (pantalla de administración de componentes).
    """
    df = _cargar_componentes(engine, [patente] if patente else None)
    return df


def _regla_para(reglas_df: pd.DataFrame, item_key: str, marca, modelo) -> dict | None:
    """Busca la regla más específica disponible para un (item_key, marca,
    modelo): exacta marca+modelo > solo marca > genérica (marca NULL).
    """
    candidatas = reglas_df[reglas_df["item_key"] == item_key]
    if candidatas.empty:
        return None
    if marca and modelo:
        exacta = candidatas[(candidatas["marca"] == marca) & (candidatas["modelo"] == modelo)]
        if not exacta.empty:
            return exacta.iloc[0].to_dict()
    if marca:
        solo_marca = candidatas[(candidatas["marca"] == marca) & (candidatas["modelo"].isna())]
        if not solo_marca.empty:
            return solo_marca.iloc[0].to_dict()
    generica = candidatas[candidatas["marca"].isna()]
    if not generica.empty:
        return generica.iloc[0].to_dict()
    return None


def _texto_intervalo(intervalo_horas, intervalo_km, intervalo_meses) -> str:
    """Texto tipo "500 horas o 3 meses calendario, lo que ocurra primero"
    -- combina las unidades que la regla tenga definidas (puede tener una,
    dos o las tres a la vez)."""
    partes = []
    if intervalo_horas:
        partes.append(f"{intervalo_horas:,.0f} horas".replace(",", "."))
    if intervalo_km:
        partes.append(f"{intervalo_km:,.0f} km".replace(",", "."))
    if intervalo_meses:
        unidad = "mes" if intervalo_meses == 1 else "meses"
        partes.append(f"{intervalo_meses} {unidad} calendario")
    if not partes:
        return "Sin dato"
    if len(partes) == 1:
        return partes[0]
    return " o ".join(partes) + ", lo que ocurra primero"


def programa_mantenimiento(engine) -> pd.DataFrame:
    """El Programa de Mantenimiento completo: para cada componente, cada
    regla conocida (la genérica y, si las hay, las específicas por marca/
    modelo) con su intervalo en texto y qué camiones de la flota tienen
    ese componente específico instalado -- para mostrar en una pantalla de
    referencia, no para calcular vencimientos (eso lo hace
    `matriz_mantenimiento`).
    """
    items_df = catalogo_items(engine)
    reglas_df = _cargar_reglas(engine)
    componentes_df = _cargar_componentes(engine)

    filas = []
    for _, item in items_df.iterrows():
        reglas_item = reglas_df[reglas_df["item_key"] == item["item_key"]]
        # La genérica (marca NULL) primero, después las específicas.
        reglas_item = pd.concat([
            reglas_item[reglas_item["marca"].isna()],
            reglas_item[reglas_item["marca"].notna()].sort_values(["marca", "modelo"]),
        ])
        for _, regla in reglas_item.iterrows():
            es_generica = pd.isna(regla["marca"])
            if es_generica:
                marca_modelo = "Genérico (sin marca conocida)"
                camiones = []  # aplica "por defecto" a cualquier camión sin componente específico -- no se enumera acá
            else:
                marca_modelo = regla["marca"] + (f" {regla['modelo']}" if pd.notna(regla["modelo"]) else "")
                filtro = (componentes_df["item_key"] == item["item_key"]) & (componentes_df["marca"] == regla["marca"])
                if pd.notna(regla["modelo"]):
                    filtro &= componentes_df["modelo"] == regla["modelo"]
                camiones = sorted(componentes_df.loc[filtro, "patente"].tolist())
            filas.append({
                "categoria": item["categoria"], "nombre": item["nombre"], "orden": item["orden"],
                "marca_modelo": marca_modelo, "es_generica": es_generica,
                "intervalo_horas": regla["intervalo_horas"], "intervalo_km": regla["intervalo_km"],
                "intervalo_meses": regla["intervalo_meses"],
                "intervalo_texto": _texto_intervalo(regla["intervalo_horas"], regla["intervalo_km"], regla["intervalo_meses"]),
                "confianza": regla["confianza"], "fuente": regla["fuente"],
                "camiones": camiones,
            })
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# Capa 3: registro de eventos
# ---------------------------------------------------------------------------

def registrar_evento(
    engine, patente: str, items: list[str], fecha, horometro=None,
    tecnico: str = "", detalle: str = "", fallas_resueltas: str = "",
    notas: str = "", registrado_por: str = "", ot_item_id: int | None = None,
) -> str:
    """Registra una parada de mantención: uno o más ítems trabajados el
    mismo día, en el mismo camión, comparten `grupo_id`. `ot_item_id` liga
    el evento al ítem de OT que lo generó (para el Certificado de
    Mantenimiento) -- se deja opcional porque este mismo helper también se
    usa para registro directo, sin pasar por una OT. Devuelve el
    `grupo_id` generado.
    """
    grupo_id = f"{patente}-{fecha}-{datetime.now().strftime('%H%M%S%f')}"
    filas = [{
        "grupo_id": grupo_id,
        "patente": patente,
        "item_key": item_key,
        "fecha": fecha.strftime("%Y-%m-%d") if hasattr(fecha, "strftime") else str(fecha),
        "horometro": horometro,
        "tecnico": tecnico or None,
        "detalle": detalle or None,
        "fallas_resueltas": fallas_resueltas or None,
        "notas": notas or None,
        "registrado_por": registrado_por or None,
        "created_at": datetime.now(),
        "ot_item_id": ot_item_id,
    } for item_key in items]
    insertar_eventos_mantenimiento(engine, filas)
    return grupo_id


def _ultimos_eventos(engine, patentes: list[str] | None = None) -> pd.DataFrame:
    """Para cada (patente, item_key), el evento más reciente (por fecha)."""
    stmt = select(eventos_mantenimiento)
    if patentes is not None:
        stmt = stmt.where(eventos_mantenimiento.c.patente.in_(patentes))
    with engine.connect() as conn:
        df = pd.read_sql(stmt, conn)
    columnas = ["patente", "item_key", "fecha", "horometro", "tecnico", "detalle", "created_at"]
    if df.empty:
        return pd.DataFrame(columns=columnas)
    df = df.sort_values("fecha").groupby(["patente", "item_key"], as_index=False).tail(1)
    return df[columnas]


def historial_evento(engine, patente: str, item_key: str) -> pd.DataFrame:
    """Historial completo (no solo el último) de un ítem en un camión --
    para el popup de detalle al hacer clic en una celda de la matriz.
    """
    stmt = (
        select(eventos_mantenimiento)
        .where(eventos_mantenimiento.c.patente == patente)
        .where(eventos_mantenimiento.c.item_key == item_key)
        .order_by(eventos_mantenimiento.c.fecha.desc())
    )
    with engine.connect() as conn:
        df = pd.read_sql(stmt, conn)
    columnas = ["fecha", "horometro", "tecnico", "detalle", "fallas_resueltas", "notas"]
    if df.empty:
        return pd.DataFrame(columns=columnas)
    return df[columnas]


# ---------------------------------------------------------------------------
# Estado de vencimiento + matriz para el dashboard
# ---------------------------------------------------------------------------

def _sumar_meses(fecha, meses: int):
    mes_total = fecha.month - 1 + meses
    anio = fecha.year + mes_total // 12
    mes = mes_total % 12 + 1
    dia = min(fecha.day, 28)  # evita desbordes de fin de mes (30/31)
    return fecha.replace(year=anio, month=mes, day=dia)


def estado_vencimiento(ultima_fecha, ultimo_horometro, regla: dict | None, hoy=None) -> dict:
    """Calcula el estado de un (patente, item_key) dado el último evento
    registrado y la regla aplicable. El criterio principal es el calendario
    (siempre calculable); las horas se muestran como dato complementario
    cuando existen, pero no reemplazan el cálculo por calendario mientras no
    tengamos una lectura de horómetro *actual* (solo tenemos la del último
    evento registrado, no en vivo).
    """
    hoy = hoy or datetime.now().date()
    confianza = (regla or {}).get("confianza", "sindato")

    if ultima_fecha is None:
        return {
            "estado": "sin_evento", "confianza": confianza,
            "proxima_fecha": None, "dias_restantes": None, "horas_restantes": None,
            "texto": "Nunca registrado",
        }

    if regla is None or regla.get("intervalo_meses") is None:
        return {
            "estado": "sin_regla", "confianza": confianza,
            "proxima_fecha": None, "dias_restantes": None, "horas_restantes": None,
            "texto": f"Última: {ultima_fecha.strftime('%d-%m-%Y')}",
        }

    proxima_fecha = _sumar_meses(ultima_fecha, regla["intervalo_meses"])
    dias_restantes = (proxima_fecha - hoy).days
    # Horas "de calendario" hasta el vencimiento (dias_restantes * 24) -- no
    # son horas de uso del equipo (no tenemos horómetro en vivo), pero dan
    # la cuenta regresiva que pidió Antonio, negativa si ya venció.
    horas_restantes = dias_restantes * 24

    if dias_restantes < 0:
        estado = "vencido"
    elif dias_restantes <= 30:
        estado = "proximo"
    else:
        estado = "ok"

    texto = proxima_fecha.strftime("%d-%m-%Y")
    if regla.get("intervalo_horas") and ultimo_horometro is not None:
        texto += f" · {ultimo_horometro}h+{regla['intervalo_horas']}h"

    return {
        "estado": estado, "confianza": confianza,
        "proxima_fecha": proxima_fecha, "dias_restantes": dias_restantes,
        "horas_restantes": horas_restantes, "texto": texto,
    }


def matriz_mantenimiento(engine, patentes: list[str] | None = None, hoy=None) -> pd.DataFrame:
    """Matriz patente x item_key para el 3er cuadrante del dashboard. Cada
    celda es un dict {estado, confianza, texto} -- se renderiza a HTML en
    app.py, igual que se hace con la matriz de Fallas.
    """
    flota_df = _load_flota(engine, patentes)
    items_df = catalogo_items(engine)
    reglas_df = _cargar_reglas(engine)
    componentes_df = _cargar_componentes(engine, patentes)
    ultimos_df = _ultimos_eventos(engine, patentes)
    hoy = hoy or datetime.now().date()

    componentes_por_patente_item = {
        (r["patente"], r["item_key"]): r for _, r in componentes_df.iterrows()
    }
    ultimo_por_patente_item = {
        (r["patente"], r["item_key"]): r for _, r in ultimos_df.iterrows()
    }

    filas = []
    for _, camion in flota_df.iterrows():
        fila = {"patente": camion["patente"], "nombre_corto": camion["nombre_corto"]}
        for _, item in items_df.iterrows():
            item_key = item["item_key"]
            comp = componentes_por_patente_item.get((camion["patente"], item_key))
            marca = comp["marca"] if comp is not None else None
            modelo = comp["modelo"] if comp is not None else None
            regla = _regla_para(reglas_df, item_key, marca, modelo)

            evento = ultimo_por_patente_item.get((camion["patente"], item_key))
            ultima_fecha = None
            ultimo_horometro = None
            if evento is not None and evento["fecha"]:
                ultima_fecha = datetime.strptime(evento["fecha"], "%Y-%m-%d").date()
                ultimo_horometro = evento["horometro"]

            fila[item_key] = estado_vencimiento(ultima_fecha, ultimo_horometro, regla, hoy)
        filas.append(fila)

    return pd.DataFrame(filas)
