"""Franjas horarias tipo agenda y cálculo de huecos ocupados (30 min)."""

from __future__ import annotations

from datetime import date
from typing import Any

from streamlit_app.appointment_agenda_slots import (
    MAX_BOOKING_DURATION_SLOTS,
    MIN_BOOKING_DURATION_SLOTS,
    duration_slots_for_existing_appointment,
)
from streamlit_app.appointment_dates import appointment_row_date
from streamlit_app.appointment_dates import appointment_time_hm


def time_slot_options() -> list[str]:
    """Franjas cada 30 min entre 08:00 y 20:00 inclusive."""
    slots: list[str] = []
    minutes = 8 * 60
    last = 20 * 60
    while minutes <= last:
        h, mm = divmod(minutes, 60)
        slots.append(f"{h:02d}:{mm:02d}")
        minutes += 30
    return slots


def busy_slot_indices_for_day(day_rows: list[dict[str, Any]], slot_list: list[str]) -> set[int]:
    busy: set[int] = set()
    n = len(slot_list)
    for row in day_rows:
        if str(row.get("status") or "").strip().lower() == "cancelada":
            continue
        hm = appointment_time_hm(row.get("appointment_date", row.get("date")))
        if hm == "—":
            continue
        try:
            start_idx = slot_list.index(hm)
        except ValueError:
            continue
        dur = duration_slots_for_existing_appointment(row)
        for j in range(start_idx, min(start_idx + dur, n)):
            busy.add(j)
    return busy


def available_start_slots(slot_list: list[str], need_slots: int, busy: set[int]) -> list[str]:
    n = len(slot_list)
    out: list[str] = []
    for i in range(n):
        if i + need_slots > n:
            break
        if any(j in busy for j in range(i, i + need_slots)):
            continue
        out.append(slot_list[i])
    return out


def appointment_last_start_slot(start_hm: str, dur_slots: int, slot_opts: list[str]) -> str:
    try:
        si = slot_opts.index(start_hm)
    except ValueError:
        return start_hm
    last_i = min(si + max(int(dur_slots), 1) - 1, len(slot_opts) - 1)
    return slot_opts[last_i]


def duration_slots_from_start_last(start_hm: str, last_slot_hm: str, slot_opts: list[str]) -> int:
    try:
        si = slot_opts.index(start_hm)
        ei = slot_opts.index(last_slot_hm)
    except ValueError:
        return MIN_BOOKING_DURATION_SLOTS
    if ei < si:
        return MIN_BOOKING_DURATION_SLOTS
    return max(
        MIN_BOOKING_DURATION_SLOTS,
        min(MAX_BOOKING_DURATION_SLOTS, ei - si + 1),
    )


def parse_existing_appointment_slot(val: Any) -> tuple[date, str]:
    d = appointment_row_date(val)
    s = str(val or "").strip().replace("T", " ")
    opts = time_slot_options()
    if len(s) >= 16:
        chunk = s[11:16]
        if chunk in opts:
            return d, chunk
    return d, "09:00" if "09:00" in opts else opts[0]


__all__ = [
    "appointment_last_start_slot",
    "available_start_slots",
    "busy_slot_indices_for_day",
    "duration_slots_from_start_last",
    "parse_existing_appointment_slot",
    "time_slot_options",
]