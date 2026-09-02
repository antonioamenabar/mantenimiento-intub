"""Componente Streamlit (`components.declare_component`) para la tabla de
Fallas del Dashboard -- vive en su propio módulo importable, y NO
directamente dentro de `dashboard/pages/dashboard.py`, a propósito:
`declare_component` necesita resolver el módulo que lo llama vía
`inspect.getmodule(caller_frame)`, y las páginas de un `st.navigation` se
ejecutan con `exec()` (sin quedar registradas en `sys.modules`), lo que
hace que esa resolución falle con `RuntimeError: module is None` -- un
módulo importado normalmente (como este) sí se resuelve bien.

Ver `dashboard/components/fallas_table/index.html` para el HTML/JS del
componente en sí, y `dashboard/pages/dashboard.py` (`render_fallas`) para
cómo se usa.
"""
from pathlib import Path

import streamlit.components.v1 as components

_COMPONENT_DIR = Path(__file__).resolve().parent.parent / "dashboard" / "components" / "fallas_table"

fallas_table = components.declare_component("fallas_table", path=str(_COMPONENT_DIR))
