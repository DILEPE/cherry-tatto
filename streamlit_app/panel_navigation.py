"""Navegación interna del panel vía `query_params` + rerun (sin recarga HTML completa).

`st.link_button` provoca navegación del navegador y en muchos despliegues de Streamlit eso **crea una sesión nueva**,
perdiendo `_panel_auth_ok` y mostrando el login al volver del flujo de firma.
"""
from __future__ import annotations

import streamlit as st


def open_contract_signing(appointment_id: int) -> None:
    st.query_params["view"] = "contract_sign"
    st.query_params["appointment_id"] = str(int(appointment_id))
    st.rerun()


def open_contract_read(contract_id: int) -> None:
    st.query_params["view"] = "contract_read"
    st.query_params["contract_id"] = str(int(contract_id))
    st.rerun()


def leave_contract_view_to_panel() -> None:
    """Quita los query params de firma/lectura de contrato y vuelve al panel (misma sesión)."""
    st.query_params.pop("view", None)
    st.query_params.pop("appointment_id", None)
    st.query_params.pop("contract_id", None)
    st.rerun()
