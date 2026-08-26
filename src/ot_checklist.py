"""Lo que el mecánico completa al cerrar una OT, por tipo de trabajo:

  - Inspección: el checklist de la ficha correspondiente (R-PR03-09 Inicio,
    R-PR03-07 Fin, R-PR03-04 Semanal), ítem por ítem -- foto, estado
    Normal/Fuera de Normal, y observación obligatoria si quedó Fuera de
    Normal.
  - Fallas: qué sistema del camión se trabajó (de una lista fija de 11) +
    foto antes/después.
  - Mantenimiento Programado: foto antes/después.

Las fotos se guardan en disco (`data/fotos_ot/<ot_id>/...`) -- para una app
de uso interno y local esto es más simple que un bucket en la nube; si el
día de mañana se pasa a Postgres/Supabase, `foto_ruta`/`ruta` seguirían
apuntando a un archivo, solo cambiaría de dónde se sirve.
"""
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import select

from src import config
from src.db import (
    inspeccion_checklist_catalogo, inspeccion_checklist_respuestas,
    ot_item_sistema, ot_item_fotos,
    replace_checklist_catalogo, guardar_respuestas_checklist,
    guardar_sistema_ot_item, guardar_foto_ot_item,
)

FOTOS_DIR = config.ROOT_DIR / "data" / "fotos_ot"

ESTADOS_CHECKLIST = ["normal", "fuera_normal", "no_aplica"]
ESTADO_LABEL = {"normal": "Normal", "fuera_normal": "Fuera de Normal", "no_aplica": "No Aplica"}

# Estados que exigen que el mecánico deje una observación obligatoria --
# "Fuera de Normal" para describir qué encontró, "No Aplica" para que el
# Jefe vaya aprendiendo en qué camiones ciertos ítems del checklist no
# corresponden (sin tocar el catálogo: eso se decide a mano, no solo, por
# eso no se borra nada automáticamente).
ESTADOS_CON_OBSERVACION_OBLIGATORIA = {"fuera_normal", "no_aplica"}

# Fuente: fichas R-PR03-09 (Inicio), R-PR03-07 (Fin), R-PR03-04 (Semanal).
# (grupo, item), en el orden de la ficha impresa.
CHECKLIST_CATALOGO = {
    "Inspección Inicio Día": [
        ("Camión", "Aceite motor"),
        ("Camión", "Líquido refrigerante"),
        ("Camión", "Neumáticos"),
        ("Equipo", "Aceite hidráulico"),
        ("Equipo", "Aceite BAP"),
        ("Equipo", "Aceite Depresor"),
    ],
    "Inspección Fin Día": [
        ("Cabina", "Cabina limpia"),
        ("Cabina", "Kilometraje"),
        ("Cabina", "Horómetro"),
        ("Cabina", "Nivel Adblue"),
        ("Cabina", "Nivel combustible"),
        ("Herramientas Succión", "Tubos de succión"),
        ("Herramientas Succión", "Abrazaderas"),
        ("Herramientas Succión", "Reducciones tubo succión"),
        ("Herramientas", "Conos"),
        ("Herramientas", "Barras conos"),
        ("Herramientas", "Mangueras grifo"),
        ("Herramientas", "Llave grifo"),
        ("Herramientas", "Adaptador grifo"),
        ("Herramientas", "Colas de tigre"),
        ("Herramientas", "Chuzo"),
        ("Herramientas", "Radios comunicación"),
        ("Herramientas", "Atriles señalética"),
        ("Herramientas", "Cartel hombres trabajando"),
        ("Herramientas", "Cartel angostamiento reversible"),
        ("Herramientas", "Cartel flecha blanca con fondo azul"),
    ],
    "Inspección Semanal": [
        ("Camión", "Aceite motor"),
        ("Camión", "Líquido refrigerante"),
        ("Camión", "Neumáticos"),
        ("Camión", "Suspensión y amortiguación"),
        ("Camión", "Correa accesorios"),
        ("Camión", "Crucetas"),
        ("Camión", "Horómetro"),
        ("Equipo", "Aceite hidráulico"),
        ("Equipo", "Aceite BAP"),
        ("Equipo", "Filtro agua BAP"),
        ("Equipo", "Aceite Depresor"),
        ("Equipo", "Filtro aire Depresor"),
        ("Equipo", "Aceite PTO"),
        ("Equipo", "Correa PTO-BAP"),
        ("Equipo", "Correa PTO-Depresor"),
        ("Equipo", "Lubricación (tornamesa y carrete manguera)"),
        ("Equipo", "Manguera AP"),
        ("Equipo", "Sistema Succión"),
        ("Equipo", "Sistema Hidráulico"),
        ("Equipo", "Sistema Eléctrico"),
        ("Equipo", "Sistema Neumático"),
        ("Equipo", "Paradas de Emergencia"),
    ],
}

# Lista fija para "sistema trabajado" en Fallas.
SISTEMAS_FALLA = [
    "Motor principal",
    "Transmisión",
    "Suspensión",
    "Ruedas, neumáticos o frenos",
    "Sistema eléctrico (incluye cableado, luces, tablero)",
    "Sistema hidráulico (brazos, bombas auxiliares, cilindros)",
    "Sistema neumático (líneas de aire, válvulas, compresor)",
    "Mangueras y conexiones (agua, vacío, presión)",
    "Sistema de aspiración / bomba de vacío (depresor)",
    "Sistema de jeteo de agua a presión",
    "Cuba de sólidos / estanque de lodos",
]


def seed_checklist_catalogo(engine):
    """Vuelca CHECKLIST_CATALOGO a la base. Idempotente (reemplaza
    completo), igual criterio que las reglas de mantención.
    """
    filas = [
        {"subtipo": subtipo, "grupo": grupo, "item": item, "orden": i}
        for subtipo, items in CHECKLIST_CATALOGO.items()
        for i, (grupo, item) in enumerate(items)
    ]
    replace_checklist_catalogo(engine, filas)


def catalogo_para_subtipo(engine, subtipo: str) -> pd.DataFrame:
    stmt = (
        select(inspeccion_checklist_catalogo)
        .where(inspeccion_checklist_catalogo.c.subtipo == subtipo)
        .order_by(inspeccion_checklist_catalogo.c.orden)
    )
    with engine.connect() as conn:
        return pd.read_sql(stmt, conn)


def guardar_foto(ot_id: int, archivo, prefijo: str = "foto") -> str:
    """Guarda el archivo subido (`st.file_uploader`) en disco y devuelve la
    ruta relativa a la raíz del proyecto, para guardar en la base.
    """
    carpeta = FOTOS_DIR / str(ot_id)
    carpeta.mkdir(parents=True, exist_ok=True)
    extension = Path(archivo.name).suffix or ".jpg"
    nombre = f"{prefijo}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}{extension}"
    ruta = carpeta / nombre
    ruta.write_bytes(archivo.getvalue())
    return str(ruta.relative_to(config.ROOT_DIR))


def ruta_absoluta(ruta_relativa: str) -> Path:
    return config.ROOT_DIR / ruta_relativa


def guardar_checklist_completo(engine, ot_id: int, ot_item_id: int, respuestas: list[dict]):
    """`respuestas`: lista de {catalogo_id, estado, observacion, archivo}
    (archivo puede ser None). Guarda la foto de cada ítem que tenga una, y
    después inserta todas las filas de respuesta de una vez.
    """
    filas = []
    for r in respuestas:
        foto_ruta = None
        if r.get("archivo") is not None:
            foto_ruta = guardar_foto(ot_id, r["archivo"], prefijo=f"chk{r['catalogo_id']}")
        filas.append({
            "ot_item_id": ot_item_id, "catalogo_id": r["catalogo_id"],
            "estado": r["estado"], "observacion": r.get("observacion") or None,
            "foto_ruta": foto_ruta,
        })
    guardar_respuestas_checklist(engine, filas)


def guardar_sistema_y_fotos(engine, ot_id: int, ot_item_id: int, sistema: str | None, foto_antes, foto_despues):
    """Para un ot_item de Fallas o Mantenimiento Programado: guarda el
    sistema trabajado (si corresponde, solo Fallas) y las fotos antes/después
    que se hayan adjuntado (ambas son opcionales por si el mecánico solo
    tiene una a mano).
    """
    if sistema:
        guardar_sistema_ot_item(engine, ot_item_id, sistema)
    if foto_antes is not None:
        ruta = guardar_foto(ot_id, foto_antes, prefijo="antes")
        guardar_foto_ot_item(engine, ot_item_id, "antes", ruta)
    if foto_despues is not None:
        ruta = guardar_foto(ot_id, foto_despues, prefijo="despues")
        guardar_foto_ot_item(engine, ot_item_id, "despues", ruta)


def checklist_de_ot_item(engine, ot_item_id: int) -> pd.DataFrame:
    """Respuestas guardadas de un ot_item de Inspección, con el nombre del
    ítem del catálogo -- para revisar una OT ya completada.
    """
    stmt = (
        select(
            inspeccion_checklist_catalogo.c.grupo, inspeccion_checklist_catalogo.c.item,
            inspeccion_checklist_respuestas.c.estado, inspeccion_checklist_respuestas.c.observacion,
            inspeccion_checklist_respuestas.c.foto_ruta,
        )
        .join(
            inspeccion_checklist_catalogo,
            inspeccion_checklist_catalogo.c.id == inspeccion_checklist_respuestas.c.catalogo_id,
        )
        .where(inspeccion_checklist_respuestas.c.ot_item_id == ot_item_id)
        .order_by(inspeccion_checklist_catalogo.c.orden)
    )
    with engine.connect() as conn:
        return pd.read_sql(stmt, conn)


def sistema_de_ot_item(engine, ot_item_id: int) -> str | None:
    stmt = select(ot_item_sistema.c.sistema).where(ot_item_sistema.c.ot_item_id == ot_item_id)
    with engine.connect() as conn:
        fila = conn.execute(stmt).fetchone()
    return fila[0] if fila else None


def fotos_de_ot_item(engine, ot_item_id: int) -> pd.DataFrame:
    stmt = select(ot_item_fotos.c.momento, ot_item_fotos.c.ruta).where(ot_item_fotos.c.ot_item_id == ot_item_id)
    with engine.connect() as conn:
        return pd.read_sql(stmt, conn)
