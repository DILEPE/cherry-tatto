"""Lógica pura compartida por el formulario de agendar (sin Streamlit).

Permite reusar combinación diseño/notas y clamp de duración desde tests u otros entrypoints.
"""

from __future__ import annotations

from streamlit_app.appointment_agenda_slots import MAX_BOOKING_DURATION_SLOTS, MIN_BOOKING_DURATION_SLOTS

BOOKING_DESIGN_DETAIL_SEP = "\n---\n"


def clamp_booking_duration_slots(raw_slots: object) -> int:
    """Franjas de 30 min entre mínimo y máximo configurados."""
    try:
        n = int(raw_slots)
    except (TypeError, ValueError):
        n = MIN_BOOKING_DURATION_SLOTS
    return max(MIN_BOOKING_DURATION_SLOTS, min(MAX_BOOKING_DURATION_SLOTS, n))


def merge_booking_design_and_notes(design: str, notes: str) -> str:
    """Texto de detalle API: diseño opcional + observaciones, mismo separador que edición desde calendario."""
    dz, nt = design.strip(), notes.strip()
    if dz and nt:
        return f"{dz}{BOOKING_DESIGN_DETAIL_SEP}{nt}"
    return dz or nt


__all__ = [
    "BOOKING_DESIGN_DETAIL_SEP",
    "clamp_booking_duration_slots",
    "merge_booking_design_and_notes",
]
