"""Autenticación simple para el Software de Mantenimiento -- cuatro roles:
"jefe" y "supervisor" (equivalentes: crean/asignan/cancelan OTs, ven el
Dashboard, administran mecánicos y talleres -- la diferencia es solo de
cargo), "mecanico" (ve y completa solo las OTs que le asignaron) y "admin"
(no opera OTs -- solo crea y administra las cuentas de Jefe/Supervisor).
Pensado para una app interna de uso local por un puñado de personas, no
para exposición a internet -- por eso es una tabla propia con contraseña
hasheada (PBKDF2, sin dependencias extra), en vez de un proveedor de
identidad externo.
"""
import hashlib
import os
from datetime import datetime

import pandas as pd
from sqlalchemy import select

from src.db import usuarios, crear_usuario, actualizar_password

_ITERACIONES = 200_000

# Roles que pueden crear/cancelar OTs y administrar mecánicos/talleres --
# "jefe" y "supervisor" tienen exactamente las mismas capacidades sobre el
# Software de Mantenimiento.
ROLES_GESTION = ("jefe", "supervisor")

ROL_LABEL = {
    "jefe": "Jefe de Mantenimiento", "supervisor": "Supervisor",
    "mecanico": "Mecánico", "admin": "Administrador",
}


def _hash_password(password: str, sal: str | None = None) -> str:
    sal = sal or os.urandom(16).hex()
    derivado = hashlib.pbkdf2_hmac("sha256", password.encode(), sal.encode(), _ITERACIONES).hex()
    return f"{sal}${derivado}"


def _verificar_password(password: str, password_hash: str) -> bool:
    try:
        sal, _ = password_hash.split("$", 1)
    except ValueError:
        return False
    return _hash_password(password, sal) == password_hash


def seed_jefe_inicial(engine, username="jefe", password="cambiar123", nombre="Jefe de Mantenimiento"):
    """Crea los primeros usuarios ("jefe" y "admin") si la tabla
    `usuarios` está vacía -- así hay cómo entrar la primera vez. La
    contraseña por defecto es intencionalmente obvia; hay que cambiarla
    desde "Mi cuenta" apenas se entra. El "admin" es quien de ahí en
    adelante crea las cuentas de Jefe/Supervisor (ver `crear_usuario_gestion`).
    """
    with engine.connect() as conn:
        alguno = conn.execute(select(usuarios.c.id)).fetchone()
    if alguno is not None:
        return
    crear_usuario(
        engine, username=username, password_hash=_hash_password(password),
        nombre=nombre, rol="jefe", created_at=datetime.now(),
    )
    crear_usuario(
        engine, username="admin", password_hash=_hash_password(password),
        nombre="Administrador", rol="admin", created_at=datetime.now(),
    )


def crear_usuario_mecanico(engine, username: str, password: str, nombre: str) -> int:
    return crear_usuario(
        engine, username=username, password_hash=_hash_password(password),
        nombre=nombre, rol="mecanico", created_at=datetime.now(),
    )


def crear_usuario_gestion(engine, username: str, password: str, nombre: str, rol: str) -> int:
    """Crea una cuenta "jefe" o "supervisor" -- lo usa el Administrador
    desde la página de Administración."""
    if rol not in ROLES_GESTION:
        raise ValueError(f"Rol inválido para una cuenta de gestión: {rol}")
    return crear_usuario(
        engine, username=username, password_hash=_hash_password(password),
        nombre=nombre, rol=rol, created_at=datetime.now(),
    )


def usuarios_de_gestion(engine) -> pd.DataFrame:
    """Cuentas "jefe"/"supervisor" existentes, para la página de
    Administración."""
    stmt = select(usuarios).where(usuarios.c.rol.in_(ROLES_GESTION))
    with engine.connect() as conn:
        return pd.read_sql(stmt, conn)


def desactivar_usuario(engine, usuario_id: int):
    with engine.begin() as conn:
        conn.execute(usuarios.update().where(usuarios.c.id == usuario_id).values(activo=False))


def cambiar_password(engine, usuario_id: int, password_nueva: str):
    actualizar_password(engine, usuario_id, _hash_password(password_nueva))


def verificar_login(engine, username: str, password: str) -> dict | None:
    """Devuelve el usuario (dict) si username/password son correctos y el
    usuario está activo, o None si no.
    """
    stmt = select(usuarios).where(usuarios.c.username == username).where(usuarios.c.activo.is_(True))
    with engine.connect() as conn:
        fila = conn.execute(stmt).mappings().first()
    if fila is None:
        return None
    if not _verificar_password(password, fila["password_hash"]):
        return None
    return dict(fila)


def usuario_actual() -> dict | None:
    """Lee el usuario logueado desde `st.session_state` -- se llama desde
    cada página para saber quién es y qué debería poder ver.
    """
    import streamlit as st
    return st.session_state.get("usuario")


def requerir_login(rol_requerido: str | tuple[str, ...] | list[str] | None = None):
    """Corta la ejecución de la página (con un mensaje) si no hay sesión
    iniciada, o si el rol no corresponde. `rol_requerido=None` solo exige
    estar logueado, sin importar el rol; puede ser un solo rol o una
    lista/tupla de roles aceptados (ej. `auth.ROLES_GESTION`).
    """
    import streamlit as st
    usuario = usuario_actual()
    if usuario is None:
        st.warning("Tienes que iniciar sesión primero. Ve a la página **Inicio**.")
        st.stop()
    if rol_requerido is not None:
        roles_ok = (rol_requerido,) if isinstance(rol_requerido, str) else tuple(rol_requerido)
        if usuario["rol"] not in roles_ok:
            etiquetas = " o ".join(ROL_LABEL.get(r, r) for r in roles_ok)
            st.warning(f"Esta página es solo para el rol **{etiquetas}**.")
            st.stop()
    return usuario
