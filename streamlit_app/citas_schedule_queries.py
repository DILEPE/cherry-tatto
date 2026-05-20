"""Consultas de ocupación por día / profesional para agenda (sin Streamlit)."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from app.domain.contract_kinds import appointment_to_contract_kind
from streamlit_app.appointment_dates import appointment_row_date


def appointments_same_day_raw(items: list[dict[str, Any]], day: date) -> list[dict[str, Any]]:
    """Citas de ese día usando la lista completa de API (sin filtrar por nombre), para no solapar huecos."""
    out: list[dict[str, Any]] = []
    for row in items:
        try:
            d = appointment_row_date(row.get("appointment_date", row.get("date")))
        except (TypeError, ValueError):
            continue
        if d != day:
            continue
        out.append(row)
    return out


def appointments_for_artist_schedule(
    items: list[dict[str, Any]],
    day: date,
    artist_id: Optional[int],
    *,
    schedule_kind: str,
    exclude_appointment_id: Optional[int] = None,
) -> list[dict[str, Any]]:
    """
    Citas que compiten por huecos: mismo profesional (o sin asignar en legacy, todas las ramas)
    y mismo tipo de agenda (`tattoo` vs `piercing`).
    """
    out: list[dict[str, Any]] = []
    for row in appointments_same_day_raw(items, day):
        rid = int(row.get("id", 0) or 0)
        if exclude_appointment_id is not None and rid == exclude_appointment_id:
            continue
        if str(row.get("status") or "").strip().lower() == "cancelada":
            continue
        if appointment_to_contract_kind(row) != schedule_kind:
            continue
        ra = row.get("assigned_panel_user_id")
        if ra is None or ra == "":
            out.append(row)
        elif artist_id is not None and int(ra) == int(artist_id):
            out.append(row)
    return out


def appointments_same_day_schedule_kind(
    items: list[dict[str, Any]],
    day: date,
    schedule_kind: str,
) -> list[dict[str, Any]]:
    """Mismo día y eje tatuaje/piercing (sin filtrar por profesional; p. ej. falta asignación)."""
    out: list[dict[str, Any]] = []
    for row in appointments_same_day_raw(items, day):
        if str(row.get("status") or "").strip().lower() == "cancelada":
            continue
        if appointment_to_contract_kind(row) != schedule_kind:
            continue
        out.append(row)
    return out


__all__ = [
    "appointments_for_artist_schedule",
    "appointments_same_day_raw",
    "appointments_same_day_schedule_kind",
]
