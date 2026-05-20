"""Etiquetas de profesional desde campos flatten de la fila de cita — sin SessionState."""

from __future__ import annotations

from typing import Any


def assigned_staff_label(row: dict[str, Any]) -> str:
    fn = str(row.get("assigned_first_name") or "").strip()
    ln = str(row.get("assigned_last_name") or "").strip()
    un = str(row.get("assigned_username") or "").strip()
    if not fn and not ln and not un:
        return "—"
    name = f"{fn} {ln}".strip()
    if name and un:
        return f"{name} (@{un})"
    if name:
        return name
    return f"@{un}" if un else "—"


def assigned_artist_display_name(row: dict[str, Any]) -> str:
    """Nombre del artista/profesional asignado (nombre y apellido; si no hay, usuario de panel)."""
    fn = str(row.get("assigned_first_name") or "").strip()
    ln = str(row.get("assigned_last_name") or "").strip()
    name = f"{fn} {ln}".strip()
    if name:
        return name
    un = str(row.get("assigned_username") or "").strip()
    if un:
        return f"@{un}"
    return "Sin asignar"


__all__ = ["assigned_artist_display_name", "assigned_staff_label"]
