"""Filtro de lista de citas como función pura (valores desde SessionState sólo en el orquestador)."""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from streamlit_app.appointment_dates import appointment_row_date


def filter_appointment_rows(
    items: list[dict[str, Any]],
    *,
    name_substr: str = "",
    service: str = "Todos",
    status: str = "Todos",
    store_id: int = 0,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> list[dict[str, Any]]:
    text = name_substr.strip().lower()
    svc = str(service or "Todos").strip() or "Todos"
    stat = str(status or "Todos").strip() or "Todos"
    sid_filter = int(store_id or 0)
    filtered: list[dict[str, Any]] = []
    for row in items:
        name_value = str(row.get("customer_name", row.get("name", "")) or "")
        service_value = str(row.get("service_type", row.get("service", "")) or "")
        status_value = str(row.get("status") or "Agendada")
        appt_date = appointment_row_date(row.get("appointment_date", row.get("date")))
        if text and text not in name_value.lower():
            continue
        if sid_filter > 0:
            try:
                row_store = int(row.get("assigned_store_id") or 0)
            except (TypeError, ValueError):
                row_store = 0
            if row_store != sid_filter:
                continue
        if svc != "Todos" and service_value != svc:
            continue
        if stat != "Todos" and status_value != stat:
            continue
        if from_date is not None and appt_date < from_date:
            continue
        if to_date is not None and appt_date > to_date:
            continue
        filtered.append(row)
    return filtered


__all__ = ["filter_appointment_rows"]
