"""Navegación interna del panel vía `query_params` + rerun (sin recarga HTML completa).

`st.link_button` provoca navegación del navegador y en muchos despliegues de Streamlit eso **crea una sesión nueva**,
perdiendo `_panel_auth_ok` y mostrando el login al volver del flujo de firma.
"""
from __future__ import annotations

from datetime import date

import streamlit as st


def open_contract_signing(appointment_id: int) -> None:
    st.query_params["view"] = "contract_sign"
    st.query_params["appointment_id"] = str(int(appointment_id))
    st.query_params.pop("contract_artist_only", None)
    st.rerun()


def open_contract_artist_signature(appointment_id: int) -> None:
    """Solo firma del profesional: sin datos ni encuesta (cliente ya firmó)."""
    st.query_params["view"] = "contract_sign"
    st.query_params["appointment_id"] = str(int(appointment_id))
    st.query_params["contract_artist_only"] = "1"
    st.rerun()


def open_contract_express_piercing() -> None:
    """Piercing: nueva cita + alta de cliente + encuesta + firma (sin appointment_id hasta crear la cita)."""
    for k in list(st.session_state.keys()):
        if isinstance(k, str) and k.startswith("ctsig_expr_"):
            st.session_state.pop(k, None)
    st.session_state.pop("ctsig_skip_init_step", None)
    st.query_params["view"] = "contract_sign"
    st.query_params["express_piercing"] = "1"
    st.query_params.pop("appointment_id", None)
    st.rerun()


def open_contract_read(contract_id: int) -> None:
    st.query_params["view"] = "contract_read"
    st.query_params["contract_id"] = str(int(contract_id))
    st.rerun()


def open_calendar_appointment_focus(appt_id: int) -> None:
    """Abre la ficha de cita en Gestión citas (misma sesión, sin recarga del navegador)."""
    aid = int(appt_id)
    if aid <= 0:
        return
    st.session_state["_cal_focus_appt_id"] = aid
    st.session_state.pop("_cal_overflow_day", None)
    for key in ("cal_appt_id", "cal_book"):
        try:
            st.query_params.pop(key, None)
        except Exception:
            pass
    st.rerun()


def open_calendar_booking_day(picked: date) -> None:
    """Abre el diálogo de agendar cita con el día precargado."""
    st.session_state.pop("_cal_focus_appt_id", None)
    st.session_state.pop("_cal_overflow_day", None)
    st.session_state["ap_ad"] = picked
    st.session_state["_ap_dlg"] = "create"
    for key in ("cal_appt_id", "cal_book"):
        try:
            st.query_params.pop(key, None)
        except Exception:
            pass
    st.rerun()


def leave_contract_view_to_panel() -> None:
    """Quita los query params de firma/lectura de contrato y vuelve al panel (misma sesión)."""
    st.query_params.pop("view", None)
    st.query_params.pop("appointment_id", None)
    st.query_params.pop("contract_id", None)
    st.query_params.pop("express_piercing", None)
    st.query_params.pop("contract_artist_only", None)
    st.rerun()
