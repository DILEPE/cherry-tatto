"""Tipo de trabajo al agendar (tatuaje, piercing, limpieza, cambio)."""

from __future__ import annotations

from typing import Any, Mapping

BOOKING_WORK_KIND_ORDER = ("piercing", "limpieza_piercing", "cambio_piercing", "tatuaje")

BOOKING_WORK_KIND_META: dict[str, dict[str, Any]] = {
    "piercing": {
        "label": "Piercing (colocación)",
        "service_token": "piercing",
        "detail_tag": "[Piercing]",
    },
    "limpieza_piercing": {
        "label": "Limpieza (piercing)",
        "service_token": "piercing",
        "detail_tag": "[Limpieza piercing]",
    },
    "cambio_piercing": {
        "label": "Cambio de piercing",
        "service_token": "piercing",
        "detail_tag": "[Cambio piercing]",
    },
    "tatuaje": {
        "label": "Tatuaje (sesión)",
        "service_token": "tattoo",
        "detail_tag": "[Tatuaje]",
    },
}


def work_kind_infer_from_existing_row(row: Mapping[str, Any]) -> str:
    """Heurística desde fila API (tipo de servicio + detalle)."""
    svc = str(row.get("service_type") or row.get("service") or "").strip().lower()
    det = str(row.get("detail") or "").lower()
    combined = f"{svc} {det}"
    if "limpieza" in det:
        return "limpieza_piercing"
    if "cambio" in det and "pierc" in combined:
        return "cambio_piercing"
    if "tatu" in combined or "tattoo" in svc:
        return "tatuaje"
    if "pierc" in combined or svc == "piercing":
        return "piercing"
    return "piercing"


def booking_work_kind_label(row: Mapping[str, Any]) -> str:
    """Etiqueta legible del tipo de trabajo (sin encuesta)."""
    kind = work_kind_infer_from_existing_row(row)
    meta = BOOKING_WORK_KIND_META.get(kind) or BOOKING_WORK_KIND_META["piercing"]
    label = str(meta.get("label") or "").strip()
    if label:
        return label
    svc = str(row.get("service_type") or row.get("service") or "").strip()
    return svc or "—"


__all__ = [
    "BOOKING_WORK_KIND_META",
    "BOOKING_WORK_KIND_ORDER",
    "booking_work_kind_label",
    "work_kind_infer_from_existing_row",
]
