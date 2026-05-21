"""Parseo de fecha/hora de citas desde filas API — sin SessionState."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


def appointment_row_date(val: Any) -> date:
    """Fecha efectiva desde `appointment_date` / ISO (fallback 1990-01-01 para datos vacíos legacy)."""
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str) and val:
        s = val.strip().replace("T", " ")
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    return date(1990, 1, 1)


def appointment_time_hm(val: Any) -> str:
    """Hora HH:MM para listados compactos; '—' si solo hay fecha."""
    if val is None:
        return "—"
    if isinstance(val, datetime):
        return val.strftime("%H:%M")
    if isinstance(val, date) and not isinstance(val, datetime):
        return "—"
    s = str(val).strip().replace("T", " ")
    if not s:
        return "—"
    for chunk, fmt in ((s[:19], "%Y-%m-%d %H:%M:%S"), (s[:16], "%Y-%m-%d %H:%M")):
        try:
            return datetime.strptime(chunk, fmt).strftime("%H:%M")
        except ValueError:
            continue
    return "—"


def combine_appointment_datetime(d: date, slot_hm: str) -> str:
    slot_hm = (slot_hm or "09:00").strip()
    parts = slot_hm.split(":")
    h = int(parts[0])
    m = int(parts[1]) if len(parts) > 1 else 0
    return f"{d.strftime('%Y-%m-%d')} {h:02d}:{m:02d}:00"


def format_appointment_created_at_display(val: Any) -> str:
    if val is None:
        return "—"
    if isinstance(val, datetime):
        return val.strftime("%d/%m/%Y %H:%M")
    s = str(val).strip()
    if len(s) >= 16:
        return s[:16].replace("T", " ")
    return s or "—"


def format_appointment_datetime_table_es(val: Any) -> str:
    """Fecha/hora para tablas (p. ej. buscador de citas)."""
    if val is None:
        return "—"
    if isinstance(val, datetime):
        dt = val
    else:
        s = str(val).strip().replace("T", " ")
        if not s:
            return "—"
        parsed: datetime | None = None
        for chunk, fmt in (
            (s[:19], "%Y-%m-%d %H:%M:%S"),
            (s[:16], "%Y-%m-%d %H:%M"),
            (s[:10], "%Y-%m-%d"),
        ):
            try:
                parsed = datetime.strptime(chunk, fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            return s
        dt = parsed
    hour = dt.hour % 12 or 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{dt.strftime('%d/%m/%Y')} {hour:02d}:{dt.strftime('%M')} {ampm}"


def format_api_datetime_compact_es(dt_str: str) -> str:
    """Presentación corta para mensajes (YYYY-MM-DD HH:MM → DD/MM/YYYY HH:MM)."""
    raw = (dt_str or "").strip().replace("T", " ")[:16]
    if len(raw) < 16:
        return raw or "—"
    try:
        dt = datetime.strptime(raw, "%Y-%m-%d %H:%M")
        return dt.strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return raw


__all__ = [
    "appointment_row_date",
    "appointment_time_hm",
    "combine_appointment_datetime",
    "format_api_datetime_compact_es",
    "format_appointment_created_at_display",
    "format_appointment_datetime_table_es",
]