"""Disponibilidad de agenda por profesional (bloques de 30 minutos).

La duración de cada cita vive en el detalle como ``[agenda_slots:N]``
(igual que el panel Angular). El servidor valida solapes al crear/reprogramar.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Mapping, Optional

from app.domain.contract_kinds import service_type_to_contract_kind

AGENDA_SLOTS_PATTERN = re.compile(r"\s*\[agenda_slots:(\d+)\]\s*$", re.IGNORECASE)
MIN_BOOKING_DURATION_SLOTS = 1
MAX_BOOKING_DURATION_SLOTS = 16
SLOT_MINUTES = 30


def clamp_duration_slots(n: int) -> int:
    return max(MIN_BOOKING_DURATION_SLOTS, min(MAX_BOOKING_DURATION_SLOTS, int(n)))


def parse_agenda_slots_marker(detail: str | None) -> Optional[int]:
    m = AGENDA_SLOTS_PATTERN.search(detail or "")
    if not m:
        return None
    try:
        return clamp_duration_slots(int(m.group(1)))
    except (TypeError, ValueError):
        return None


def default_duration_slots(service_type: str | None, detail: str | None = None) -> int:
    """Misma heurística que el panel cuando no hay marcador ``[agenda_slots:N]``."""
    det = (detail or "").lower()
    svc = (service_type or "").lower()
    combined = f"{svc} {det}"
    if "limpieza" in svc or "limpieza" in det:
        return 1
    if "cambio" in svc or ("cambio" in det and "pierc" in combined):
        return 1
    if "tatu" in combined or "tattoo" in svc:
        return 4
    if "pierc" in combined:
        return 2
    return 2


def duration_slots_for_appointment(service_type: str | None, detail: str | None) -> int:
    marked = parse_agenda_slots_marker(detail)
    if marked is not None:
        return marked
    return default_duration_slots(service_type, detail)


def parse_appointment_datetime(raw: str | datetime | None) -> Optional[datetime]:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.replace(second=0, microsecond=0)
    s = str(raw).strip().replace("T", " ")
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    if len(s) >= 10:
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").replace(hour=9, minute=0)
        except ValueError:
            return None
    return None


def appointment_time_window(
    start: datetime,
    duration_slots: int,
) -> tuple[datetime, datetime]:
    slots = clamp_duration_slots(duration_slots)
    end = start + timedelta(minutes=SLOT_MINUTES * slots)
    return start, end


def windows_overlap(
    start_a: datetime,
    end_a: datetime,
    start_b: datetime,
    end_b: datetime,
) -> bool:
    return start_a < end_b and start_b < end_a


def same_schedule_kind(service_a: str | None, service_b: str | None) -> bool:
    return service_type_to_contract_kind(service_a) == service_type_to_contract_kind(service_b)


def find_schedule_conflict(
    *,
    candidate_start: datetime,
    candidate_service: str | None,
    candidate_detail: str | None,
    day_rows: list[Mapping[str, Any]],
    exclude_appointment_id: Optional[int] = None,
) -> Optional[Mapping[str, Any]]:
    """
    Devuelve la primera cita del día que solapa con el candidato
    (mismo tipo tatuaje/piercing; ya filtradas por artista / sin asignar).
    """
    cand_slots = duration_slots_for_appointment(candidate_service, candidate_detail)
    cand_start, cand_end = appointment_time_window(candidate_start, cand_slots)

    for row in day_rows:
        rid = int(row.get("id") or 0)
        if exclude_appointment_id is not None and rid == int(exclude_appointment_id):
            continue
        status = str(row.get("status") or "").strip()
        if status.lower() == "cancelada":
            continue
        svc = str(row.get("service_type") or row.get("service") or "")
        if not same_schedule_kind(candidate_service, svc):
            continue
        other_start = parse_appointment_datetime(row.get("appointment_date") or row.get("date"))
        if other_start is None:
            continue
        other_slots = duration_slots_for_appointment(svc, str(row.get("detail") or ""))
        other_s, other_e = appointment_time_window(other_start, other_slots)
        if windows_overlap(cand_start, cand_end, other_s, other_e):
            return row
    return None


def schedule_conflict_message(conflicting: Mapping[str, Any]) -> str:
    cid = conflicting.get("id")
    when = parse_appointment_datetime(
        conflicting.get("appointment_date") or conflicting.get("date")
    )
    when_s = when.strftime("%H:%M") if when else "—"
    name = str(conflicting.get("customer_name") or "").strip()
    if name:
        return (
            f"El horario se solapa con la cita #{cid} ({name}) a las {when_s}. "
            "Elige otra hora de inicio o de fin."
        )
    return (
        f"El horario se solapa con la cita #{cid} (inicio {when_s}). "
        "Elige otra hora de inicio o de fin."
    )


__all__ = [
    "AGENDA_SLOTS_PATTERN",
    "MAX_BOOKING_DURATION_SLOTS",
    "MIN_BOOKING_DURATION_SLOTS",
    "SLOT_MINUTES",
    "appointment_time_window",
    "clamp_duration_slots",
    "default_duration_slots",
    "duration_slots_for_appointment",
    "find_schedule_conflict",
    "parse_agenda_slots_marker",
    "parse_appointment_datetime",
    "same_schedule_kind",
    "schedule_conflict_message",
    "windows_overlap",
]
