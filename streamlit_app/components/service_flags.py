"""Badges HTML de tipo de servicio."""

from __future__ import annotations

import html as html_mod
from typing import Any


def service_type_flag_html(row: dict[str, Any]) -> str:
    """Insignia de tipo de servicio (diálogo citas del día)."""
    raw = str(row.get("service_type") or "").strip()
    if not raw:
        return '<span class="svc-flag svc-flag-unknown" title="Tipo de servicio">—</span>'
    key = raw.lower()
    if "tatu" in key or key == "tattoo":
        cls = "svc-flag-tattoo"
    elif "pierc" in key or key == "piercing":
        cls = "svc-flag-piercing"
    elif "limpieza" in key:
        cls = "svc-flag-limpieza"
    elif "cambio" in key:
        cls = "svc-flag-cambio"
    else:
        cls = "svc-flag-other"
    return (
        f'<span class="svc-flag {cls}" title="Tipo de servicio">'
        f"{html_mod.escape(raw)}</span>"
    )


__all__ = ["service_type_flag_html"]
