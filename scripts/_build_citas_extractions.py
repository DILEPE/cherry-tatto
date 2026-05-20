"""Genera un borrador de citas_agendar_dialog.py cortando rangos fijos de citas_tab.py.

Ver scripts/README-citas-tab-refactor.md (rangos 98-182, 783-855, 858-1323).
Sobrescribe streamlit_app/citas_agendar_dialog.py; revisar diff antes de commitear.
"""

from pathlib import Path

root = Path(__file__).resolve().parent.parent
tab = root / "streamlit_app" / "citas_tab.py"
lines = tab.read_text(encoding="utf-8").splitlines(keepends=True)


def slice_lines(start: int, end: int) -> str:
    return "".join(lines[start - 1 : end])


chunk_bc = slice_lines(98, 182)
chunk_form = slice_lines(783, 855)
chunk_dialog = slice_lines(858, 1323)

header = '''"""Diálogo Streamlit para agendar cita nueva (formulario documento/cliente/franjas).

El calendario debe llamar `pop_booking_document_session` antes de fijar `ap_ad` desde la rejilla.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

import streamlit as st
from pydantic import ValidationError

from app.domain.appointment_money import MIN_APPOINTMENT_TOTAL_COP, format_cop
from app.schemas.customer import CUSTOMER_BIRTH_PENDING, CustomerCreate
from streamlit_app import api_client
from streamlit_app.appointment_agenda_slots import (
    MAX_BOOKING_DURATION_SLOTS,
    MIN_BOOKING_DURATION_SLOTS,
    append_agenda_slots_marker,
)
from streamlit_app.appointment_dates import appointment_row_date, combine_appointment_datetime
from streamlit_app.appointment_slots import (
    available_start_slots,
    busy_slot_indices_for_day,
    time_slot_options,
)
from streamlit_app.citas_booking_meta import (
    BOOKING_WORK_KIND_META,
    BOOKING_WORK_KIND_ORDER,
    service_and_detail_for_work_kind,
    work_kind_to_assignee_role,
    work_kind_to_schedule_kind,
)
from streamlit_app.citas_panel_staff import ensure_assignable_staff
from streamlit_app.citas_schedule_queries import (
    appointments_for_artist_schedule,
    appointments_same_day_schedule_kind,
)
from streamlit_app.customer_sync import fetch_customer_by_document
from streamlit_app.http_error_detail import format_http_error_detail
from streamlit_app.state.appointment_keys import KEY_ACTION_INFO
from streamlit_app.validation import validate_appointment


def queue_appointment_action_success(msg: str) -> None:
    """Confirmación visible en la siguiente ejecución (pestaña Citas o Reporte)."""
    st.session_state[KEY_ACTION_INFO] = msg


'''

combined = chunk_bc + "\n\n" + chunk_form + "\n\n" + chunk_dialog

repls = [
    ("def _booking_customer_create_for_existing_client", "def booking_customer_create_for_existing_client"),
    ("def _init_appt_form_state_once", "def init_appt_form_state_once"),
    ("def _pop_booking_document_session", "def pop_booking_document_session"),
    ("def _reset_appointment_form_state", "def reset_appointment_form_state"),
    ("_pop_booking_document_session()", "pop_booking_document_session()"),
    ("_init_appt_form_state_once()", "init_appt_form_state_once()"),
    ("_reset_appointment_form_state()", "reset_appointment_form_state()"),
    ("def _initial_receipt_success_message", "def initial_receipt_success_message"),
    ("_initial_receipt_success_message(", "initial_receipt_success_message("),
    ("def _booking_observations_and_design_for_api", "def booking_observations_and_design_for_api"),
    ("_booking_observations_and_design_for_api()", "booking_observations_and_design_for_api()"),
    ("def _booking_duration_slots_from_session", "def booking_duration_slots_from_session"),
    ("_booking_duration_slots_from_session()", "booking_duration_slots_from_session()"),
    ("def _show_validation_errors", "def show_validation_errors"),
    ("_show_validation_errors(", "show_validation_errors("),
    ("def _dialog_agendar_cita", "def dialog_agendar_cita"),
]

for a, b in repls:
    combined = combined.replace(a, b)

combined = combined.replace("_time_slot_options()", "time_slot_options()")
combined = combined.replace("_MIN_APPOINTMENT_TOTAL_COP", "MIN_APPOINTMENT_TOTAL_COP")
combined = combined.replace("_BOOKING_WORK_KIND_ORDER", "BOOKING_WORK_KIND_ORDER")
combined = combined.replace("_BOOKING_WORK_KIND_META", "BOOKING_WORK_KIND_META")
combined = combined.replace("_ensure_assignable_staff()", "ensure_assignable_staff()")
combined = combined.replace("_work_kind_to_assignee_role", "work_kind_to_assignee_role")
combined = combined.replace("_work_kind_to_schedule_kind", "work_kind_to_schedule_kind")
combined = combined.replace("_appointments_for_artist_schedule", "appointments_for_artist_schedule")
combined = combined.replace("_appointments_same_day_schedule_kind", "appointments_same_day_schedule_kind")
combined = combined.replace("_busy_slot_indices_for_day", "busy_slot_indices_for_day")
combined = combined.replace("_available_start_slots", "available_start_slots")
combined = combined.replace("_append_agenda_slots_marker", "append_agenda_slots_marker")
combined = combined.replace("_combine_appointment_datetime", "combine_appointment_datetime")
combined = combined.replace("_service_and_detail_for_work_kind", "service_and_detail_for_work_kind")
combined = combined.replace("_booking_customer_create_for_existing_client", "booking_customer_create_for_existing_client")
combined = combined.replace("_api_error(", "format_http_error_detail(")
combined = combined.replace("_queue_appointment_action_success", "queue_appointment_action_success")

combined = combined.replace("_MIN_BOOKING_DURATION_SLOTS", "MIN_BOOKING_DURATION_SLOTS")
combined = combined.replace("_MAX_BOOKING_DURATION_SLOTS", "MAX_BOOKING_DURATION_SLOTS")

combined = combined.replace("_parse_date(", "appointment_row_date(")

footer = """

__all__ = [
    "booking_customer_create_for_existing_client",
    "dialog_agendar_cita",
    "init_appt_form_state_once",
    "pop_booking_document_session",
    "queue_appointment_action_success",
    "reset_appointment_form_state",
]
"""

out_path = root / "streamlit_app" / "citas_agendar_dialog.py"
out_path.write_text(header + combined + footer, encoding="utf-8")
print("Wrote", out_path)
