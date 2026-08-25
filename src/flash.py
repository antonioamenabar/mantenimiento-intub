"""Mensajes que sobreviven a un `st.rerun()`. Sin esto, un
`st.success("...")` seguido de `st.rerun()` nunca llega a mostrarse -- el
rerun corta el script antes de que el usuario vea el mensaje.
"""
import streamlit as st


def flash(kind: str, mensaje: str):
    """Guarda un mensaje para mostrarlo recién en el próximo render (justo
    antes de un `st.rerun()`). `kind` es el nombre de un método de
    streamlit: "success", "warning", "error", "info".
    """
    st.session_state["_flash"] = (kind, mensaje)


def mostrar_flash():
    """Muestra (y limpia) el mensaje pendiente, si hay uno. Llamar al
    principio de cada página, después del guard de login.
    """
    pendiente = st.session_state.pop("_flash", None)
    if pendiente:
        kind, mensaje = pendiente
        getattr(st, kind)(mensaje)
