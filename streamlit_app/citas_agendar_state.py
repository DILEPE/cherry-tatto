"""Estado de sesión Streamlit para el formulario «Agendar cita» (clave `ap_*` y caches de verificación).

Otros tabs o flujos pueden reutilizar las mismas claves llamando `init_appt_form_state_once` y los `render_*` de
`citas_agendar_sections` sin abrir el `@st.dialog` (p. ej. asistentes de cita express).
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict

import streamlit as st

from app.domain.appointment_money import MIN_APPOINTMENT_TOTAL_COP
from streamlit_app.appointment_slots import time_slot_options
from streamlit_app.state.appointment_keys import KEY_ACTION_INFO


def queue_appointment_action_success(msg: str) -> None:
    """Confirmación visible en la siguiente ejecución (pestaña Citas o Reporte)."""
    st.session_state[KEY_ACTION_INFO] = msg


def init_appt_form_state_once() -> None:
    if st.session_state.get("_ap_form_ready"):
        return
    slot_opts = time_slot_options()
    default_slot = "09:00" if "09:00" in slot_opts else slot_opts[0]
    defaults: Dict[str, Any] = {
        "ap_fn": "",
        "ap_ln": "",
        "ap_phone": "",
        "ap_email": "",
        "ap_ad": date.today(),
        "ap_slot": default_slot,
        "ap_det": "",
        "ap_design": "",
        "ap_dep": float(MIN_APPOINTMENT_TOTAL_COP),
        "ap_total": float(MIN_APPOINTMENT_TOTAL_COP),
        "ap_priority": False,
        "ap_duration_slots": 1,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    if "ap_work_kind" not in st.session_state:
        st.session_state["ap_work_kind"] = "piercing"
    if st.session_state.get("ap_work_kind") == "limpieza_tatuaje":
        st.session_state["ap_work_kind"] = "limpieza_piercing"
    if "ap_doc_type" not in st.session_state:
        st.session_state["ap_doc_type"] = "CC"
    st.session_state["_ap_form_ready"] = True


def pop_booking_document_session() -> None:
    """Llamar antes de fijar `ap_ad` desde calendario / rejilla para no arrastrar un cliente anterior."""
    for k in (
        "_ap_booking_customer_id",
        "_ap_booking_customer_snapshot",
        "_ap_need_new_customer",
        "_ap_doc_verified",
        "_ap_verify_msg",
        "_ap_verify_level",
        "_ap_verified_doc_number",
        "_ap_pending_doc_type_sync",
        "ap_doc_number",
    ):
        st.session_state.pop(k, None)


def reset_appointment_form_state() -> None:
    for key in (
        "ap_fn",
        "ap_ln",
        "ap_phone",
        "ap_email",
        "ap_ad",
        "ap_slot",
        "ap_det",
        "ap_design",
        "ap_dep",
        "ap_total",
        "ap_priority",
        "ap_work_kind",
        "ap_doc_type",
        "ap_assigned_staff_id",
        "ap_duration_slots",
        "ex_full_name",
    ):
        st.session_state.pop(key, None)
    st.session_state["_ap_form_ready"] = False
    pop_booking_document_session()


__all__ = [
    "init_appt_form_state_once",
    "pop_booking_document_session",
    "queue_appointment_action_success",
    "reset_appointment_form_state",
]
