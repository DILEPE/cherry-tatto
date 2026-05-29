"""Diálogo Streamlit para agendar cita nueva — orquestador fino sobre piezas modulares.

Componentes:
- Estado y colas: `citas_agendar_state`
- Cuerpo reutilizable: `render_agendar_booking_form_body` (`citas_agendar_sections`)
- Alta remota (POST): `citas_agendar_submit`

Otros flujos pueden componer el mismo UI sin registrar este `@st.dialog` llamando a
``render_agendar_booking_form_body`` y ``render_agendar_create_cancel_footer`` después de
``init_appt_form_state_once`` y usando las mismas claves ``ap_*``.

El calendario debe llamar `pop_booking_document_session` antes de fijar `ap_ad` desde la rejilla.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from app.domain.appointment_money import MIN_APPOINTMENT_TOTAL_COP
from streamlit_app.appointment_dates import appointment_row_date
from streamlit_app.citas_agendar_customer import booking_customer_create_for_existing_client
from streamlit_app.citas_agendar_sections import (
    render_agendar_booking_form_body,
    sync_pending_booking_document_type,
)
from streamlit_app.citas_agendar_state import (
    init_appt_form_state_once,
    pop_booking_document_session,
    queue_appointment_action_success,
    reset_appointment_form_state,
)
from streamlit_app.citas_agendar_submit import handle_agendar_booking_submit, render_agendar_create_cancel_footer


__all__ = [
    "booking_customer_create_for_existing_client",
    "dialog_agendar_cita",
    "handle_agendar_booking_submit",
    "init_appt_form_state_once",
    "pop_booking_document_session",
    "queue_appointment_action_success",
    "render_agendar_booking_form_body",
    "render_agendar_create_cancel_footer",
    "reset_appointment_form_state",
]


@st.dialog("Agendar cita", width="large", dismissible=False)
def dialog_agendar_cita() -> None:
    init_appt_form_state_once()
    if float(st.session_state.get("ap_total") or 0) < float(MIN_APPOINTMENT_TOTAL_COP):
        st.session_state["ap_total"] = float(MIN_APPOINTMENT_TOTAL_COP)
    if float(st.session_state.get("ap_dep") or 0) < float(MIN_APPOINTMENT_TOTAL_COP):
        st.session_state["ap_dep"] = float(MIN_APPOINTMENT_TOTAL_COP)

    sync_pending_booking_document_type()

    picked_raw = st.session_state.get("ap_ad")
    if picked_raw is None:
        st.error("Selecciona un día en el calendario para agendar.")
        if st.button("Cerrar", use_container_width=True, key="btn_appt_close_no_day"):
            st.session_state.pop("_ap_dlg", None)
            st.rerun()
        return

    picked = picked_raw if isinstance(picked_raw, date) else appointment_row_date(picked_raw)
    today_d = date.today()
    if picked < today_d:
        st.error("No se pueden agendar citas en fechas pasadas. Elige un día de hoy en adelante en el calendario.")
        if st.button("Cerrar", use_container_width=True, key="btn_appt_close_past_date"):
            st.session_state.pop("_ap_dlg", None)
            st.rerun()
        return

    render_agendar_booking_form_body(picked=picked)
    render_agendar_create_cancel_footer(picked=picked, today_d=today_d)
