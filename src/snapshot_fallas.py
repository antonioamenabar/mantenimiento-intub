"""Guarda una foto histórica del cuadrante de Fallas para la semana que
recién cerró. Pensado para correr automáticamente cada lunes a las 8:00 AM
(vía Tarea Programada de Windows) -- también se puede correr a mano.

Uso:
    python -m src.snapshot_fallas
"""
import sys
from datetime import datetime, timedelta, timezone

from src import db, queries, datascope_client

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


def main():
    engine = db.init_db()

    # Sincroniza tickets frescos antes de tomar la foto -- si no, se
    # guardaría el estado de la última vez que alguien corrió `src.sync` a
    # mano, no el estado real del lunes en la mañana.
    print("Sincronizando tickets desde Datascope...")
    ahora_utc = datetime.now(timezone.utc)
    tickets_frescos = datascope_client.fetch_normalized_tickets_no_cerrados()
    db.replace_tickets(engine, tickets_frescos, synced_at=ahora_utc)
    print(f"  {len(tickets_frescos)} tickets sincronizados.")

    hoy = datetime.now()
    lunes_actual = (hoy - timedelta(days=hoy.weekday())).date()
    semana_cerrada = lunes_actual - timedelta(days=7)  # la semana que recién terminó

    todas_patentes = queries.opciones_patentes(engine)
    patentes_activas = todas_patentes.loc[todas_patentes["activo"], "patente"].tolist()
    tabla = queries.matriz_fallas(engine, patentes=patentes_activas)

    filas = []
    for _, row in tabla.iterrows():
        filas.append({
            "semana_inicio": semana_cerrada.strftime("%Y-%m-%d"),
            "patente": row["patente"],
            "nombre_corto": row["nombre_corto"],
            "critica": int(row["Crítica"]),
            "alta": int(row["Alta"]),
            "media": int(row["Media"]),
            "baja": int(row["Baja"]),
            "menos_7_dias": int(row["Menos de 7 días"]),
            "entre_8_20_dias": int(row["Entre 8 y 20 días"]),
            "mas_20_dias": int(row["Más de 20 días"]),
            "total": int(row["Total"]),
        })

    db.upsert_fallas_historico(engine, filas, snapshot_at=datetime.now(timezone.utc))
    print(f"Foto histórica de Fallas guardada para la semana del {semana_cerrada} ({len(filas)} camiones).")


if __name__ == "__main__":
    main()
