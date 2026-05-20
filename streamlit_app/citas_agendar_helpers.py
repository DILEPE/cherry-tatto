"""Helpers de UI y lectura de estado para agendar citas desde varios puntos del panel."""

from __future__ import annotations

from typing import List

import streamlit as st

from streamlit_app.citas_agendar_pure import clamp_booking_duration_slots, merge_booking_design_and_notes
from streamlit_app.validation import FieldError


def initial_receipt_success_message(_dep_created: float, _service_str: str) -> str:
    """Notificación tras crear cita desde el panel (solo confirmación)."""
    return "La cita ha sido agendada."


def booking_duration_slots_from_session() -> int:
    return clamp_booking_duration_slots(st.session_state.get("ap_duration_slots"))


def booking_observations_and_design_for_api() -> str:
    return merge_booking_design_and_notes(
        str(st.session_state.get("ap_design") or ""),
        str(st.session_state.get("ap_det") or ""),
    )


def show_validation_errors(errors: List[FieldError]) -> None:
    for fe in errors:
        st.error(f"{fe.field}: {fe.message}")


__all__ = [
    "booking_duration_slots_from_session",
    "booking_observations_and_design_for_api",
    "initial_receipt_success_message",
    "show_validation_errors",
]
