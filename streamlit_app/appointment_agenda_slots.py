"""Duración en franjas de 30 min y marcador `[agenda_slots:N]` en el detalle de cita."""

from __future__ import annotations

import re
from typing import Any, Optional

AGENDA_SLOTS_DETAIL_PATTERN = re.compile(r"\s*\[agenda_slots:(\d+)\]\s*$", re.IGNORECASE)

MIN_BOOKING_DURATION_SLOTS = 1
MAX_BOOKING_DURATION_SLOTS = 16


def append_agenda_slots_marker(detail: Optional[str], slots: int) -> str:
    """Añade marcador al final del detalle para calcular ocupación real en agenda."""
    n = max(MIN_BOOKING_DURATION_SLOTS, min(MAX_BOOKING_DURATION_SLOTS, int(slots)))
    base = (detail or "").strip()
    return (f"{base} [agenda_slots:{n}]").strip() if base else f"[agenda_slots:{n}]"


def duration_slots_for_existing_appointment(row: dict[str, Any]) -> int:
    """Franjas de 30 min ocupadas: prioridad a `[agenda_slots:N]`; si no, heurística por servicio."""
    det_full = str(row.get("detail") or "")
    m = AGENDA_SLOTS_DETAIL_PATTERN.search(det_full)
    if m:
        try:
            return max(
                MIN_BOOKING_DURATION_SLOTS,
                min(MAX_BOOKING_DURATION_SLOTS, int(m.group(1))),
            )
        except ValueError:
            pass
    svc = str(row.get("service_type") or row.get("service") or "").strip().lower()
    det = det_full.strip().lower()
    combined = f"{svc} {det}"
    if "limpieza" in det:
        return 1
    if "cambio" in det and "pierc" in combined:
        return 1
    if "tatu" in combined or "tattoo" in svc:
        return 4
    if "pierc" in combined or svc == "piercing":
        return 2
    if "other" in svc or "otro" in svc:
        return 1
    return 2


__all__ = [
    "AGENDA_SLOTS_DETAIL_PATTERN",
    "MAX_BOOKING_DURATION_SLOTS",
    "MIN_BOOKING_DURATION_SLOTS",
    "append_agenda_slots_marker",
    "duration_slots_for_existing_appointment",
]
