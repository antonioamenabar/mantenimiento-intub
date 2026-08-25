"""Autenticación simple para el Software de Mantenimiento -- dos roles:
"jefe" (crea y asigna OTs, ve el Dashboard) y "mecanico" (ve y completa
solo las OTs que le asignaron). Pensado para una app interna de uso local
por un puñado de personas, no para exposición a internet -- por eso es
una tabla propia con contraseña hasheada (PBKDF2, sin dependencias extra),
en vez de un proveedor de identidad externo.
"""
import hashlib
import os
from datetime import datetime

from sqlalchemy import select

from src.db import usuarios, crear_usuario, actualizar_password

_ITERACIONES = 200_000


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
    """Crea el primer usuario (rol "jefe") si la tabla `usuarios` está
    vacía -- así hay cómo entrar la primera vez. La contraseña por defecto
    es intencionalmente obvia; hay que cambiarla desde "Mi cuenta" apenas
    se entra.
    """
    with engine.connect() as conn:
        alguno = conn.execute(select(usuarios.c.id)).fetchone()
    if alguno is not None:
        return
    crear_usuario(
        engine, username=username, password_hash=_hash_password(password),
        nombre=nombre, rol="jefe", created_at=datetime.now(),
    )


def crear_usuario_mecanico(engine, username: str, password: str, nombre: str) -> int:
    return crear_usuario(
        engine, username=username, password_hash=_hash_password(password),
        nombre=nombre, rol="mecanico", created_at=datetime.now(),
    )


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


def requerir_login(rol_requerido: str | None = None):
    """Corta la ejecución de la página (con un mensaje) si no hay sesión
    iniciada, o si el rol no corresponde. `rol_requerido=None` solo exige
    estar logueado, sin importar el rol.
    """
    import streamlit as st
    usuario = usuario_actual()
    if usuario is None:
        st.warning("Tienes que iniciar sesión primero. Ve a la página **Inicio**.")
        st.stop()
    if rol_requerido and usuario["rol"] != rol_requerido:
        st.warning(f"Esta página es solo para el rol **{rol_requerido}**.")
        st.stop()
    return usuario
