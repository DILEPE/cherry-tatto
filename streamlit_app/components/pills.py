"""Pastillas de estado y cliente para citas — HTML puro sin `st.*`."""

from __future__ import annotations

import html as html_mod
from typing import Any


def row_is_priority(row: dict[str, Any]) -> bool:
    v = row.get("is_priority")
    if v is True or v == 1:
        return True
    if isinstance(v, str) and v.strip().lower() in ("1", "true", "yes"):
        return True
    return False


def _normalize_phone_digits(phone: Any) -> str:
    return "".join(c for c in str(phone or "") if c.isdigit())


def client_history_key(row: dict[str, Any]) -> str:
    """Clave estable para contar citas históricas por cliente (id, teléfono o nombre)."""
    cid = row.get("customer_id")
    if cid is not None and str(cid).strip() != "":
        try:
            return f"id:{int(cid)}"
        except (TypeError, ValueError):
            pass
    ph = _normalize_phone_digits(row.get("phone"))
    if ph:
        return f"ph:{ph}"
    nm = str(row.get("customer_name") or row.get("name") or "").strip().lower()
    if nm:
        return f"nm:{nm}"
    return f"row:{row.get('id', 0)}"


def client_pill_class(row: dict[str, Any], counts_by_client: dict[str, int]) -> str:
    """
    Prioridad de etiqueta: Cancelada > Reprogramada > Prioritaria >
    Cliente recurrente (>1 cita) > Cliente nuevo.
    """
    stv = str(row.get("status") or "").strip().lower()
    if stv == "cancelada":
        return "cli-pill-cancelada"
    if stv == "reprogramada":
        return "cli-pill-reprogramada"
    if row_is_priority(row):
        return "cli-pill-priority"
    key = client_history_key(row)
    if counts_by_client.get(key, 0) > 1:
        return "cli-pill-returning"
    return "cli-pill-new"


def status_pill_html(status: str) -> str:
    normalized = (status or "Agendada").strip().lower()
    cls = {
        "agendada": "pill-agendada",
        "reprogramada": "pill-reprogramada",
        "cancelada": "pill-cancelada",
        "finalizada": "pill-finalizada",
    }.get(normalized, "pill-default")
    lbl = html_mod.escape(status or "Agendada")
    return f'<span class="ap-pill {cls}">{lbl}</span>'


def customer_name_pill_html(row: dict[str, Any], counts_by_client: dict[str, int]) -> str:
    name = str(row.get("customer_name") or row.get("name") or "").strip() or "—"
    cls = client_pill_class(row, counts_by_client)
    return (
        f'<span class="cli-pill {cls} cli-pill--report-inline">'
        f"{html_mod.escape(name)}"
        "</span>"
    )


__all__ = [
    "client_history_key",
    "client_pill_class",
    "customer_name_pill_html",
    "row_is_priority",
    "status_pill_html",
]
