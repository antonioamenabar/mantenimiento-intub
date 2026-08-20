# Proyecto Mantenimiento - Intub

Dashboard para el Jefe de Mantenimiento, con 4 cuadrantes:
**Inspecciones · Fallas · Mantenimiento Programado · Inventario**.

## Estado actual

- ✅ **Inspecciones**: funcional (cumplimiento diario y semanal), conectado a Datascope.
- ⏳ Fallas, Mantenimiento Programado, Inventario: pendientes.

## Fuente de datos: Datascope

Toda la información de inspecciones y fallas vive en un único formulario de
Datascope: **"R-PR03-01 Formulario de Mantenimiento de Equipos"**
(`form_id = 658357`). El campo `Tipo de Mantenimiento` distingue el tipo de
registro:

| Tipo de Mantenimiento | Cuadrante |
|---|---|
| Inspección Diaria Inicio | Inspecciones |
| Inspección Diaria Fin | Inspecciones |
| Inspección Semanal | Inspecciones |
| Mantención Correctiva Base (solución falla) | Fallas |
| Mantención Correctiva Terreno (solución falla) | Fallas |

Nota: los formularios "R-PR02-02 Checklist Inicio Jornada" y "R-PR02-08
Checklist Fin de Jornada" son checklists de herramientas del operador, **no**
inspecciones mecánicas del camión — no se usan en este dashboard.

Documentación de la API: https://dscope.github.io/docs/ (no confundir con
"DataScope Select" de LSEG/Refinitiv, que es un producto financiero distinto).

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# completar DATASCOPE_API_KEY en .env
```

## Uso

```bash
# 1. Cargar/actualizar el maestro de flota (revisar antes data/flota_inicial.csv)
python -m src.seed_flota

# 2. Traer datos frescos desde Datascope
python -m src.sync

# 3. Levantar el dashboard
streamlit run dashboard/app.py
```

Por defecto usa una base SQLite local (`data/mantenimiento.db`, ignorada por
git). Para apuntar a Supabase, completar `DB_BACKEND=postgres` y
`DATABASE_URL` en `.env` — el resto del código no cambia.

## Pendiente / a revisar

- `data/flota_inicial.csv` tiene camiones marcados con `revisar=true`:
  patentes vistas en Datascope sin carpeta conocida en Drive, y camiones de
  Drive sin patente confirmada. Completar y corregir.
- El endpoint de Datascope `metadata_objects` (para traer la flota directo
  desde su lista de "assets") devolvió `null` en las pruebas — quedó
  pendiente investigar el nombre correcto del `metadata_type` o si requiere
  otro permiso de API key.
- Definir dónde vivirá la base de datos definitiva (Supabase: falta que se
  cree el proyecto o se decida reusar `reportes-intub`).
