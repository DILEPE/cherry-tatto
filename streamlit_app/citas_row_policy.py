"""Reglas por fila Citas sin Streamlit pesado."""

from __future__ import annotations

from typing import Any, Dict


def reprogram_disabled_for_row(r: Dict[str, Any]) -> bool:
    """Reprogramar solo en Agendada/Reprogramada, sin contrato firmado y no cancelada."""
    appt_id = int(r.get("id", 0) or 0)
    status = str(r.get("status") or "Agendada")
    if appt_id <= 0 or status == "Cancelada":
        return True
    if status not in {"Agendada", "Reprogramada"}:
        return True
    if bool(r.get("has_signed_contract")):
        return True
    return False


__all__ = ["reprogram_disabled_for_row"]
