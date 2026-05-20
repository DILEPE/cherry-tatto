"""Tipo de trabajo al agendar, etiquetas API y ejes tatuaje/piercing."""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.domain.service_types import resolve_service_type

BOOKING_WORK_KIND_ORDER = ("piercing", "limpieza_piercing", "cambio_piercing", "tatuaje")

BOOKING_WORK_KIND_META: Dict[str, Dict[str, Any]] = {
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


def service_and_detail_for_work_kind(kind: str, user_detail: str) -> tuple[str, Optional[str]]:
    meta = BOOKING_WORK_KIND_META.get(kind) or BOOKING_WORK_KIND_META["piercing"]
    svc = resolve_service_type(meta["service_token"])
    tag = meta["detail_tag"]
    extra = (user_detail or "").strip()
    if extra:
        return svc, f"{tag} {extra}".strip()
    return svc, tag


def work_kind_to_assignee_role(work_kind: str) -> str:
    if work_kind == "tatuaje":
        return "tatuador"
    return "perforador"


def work_kind_to_schedule_kind(work_kind: str) -> str:
    """
    Eje de agenda: solo sesión de tatuaje vs todo lo de piercing (colocación, limpieza, cambio).
    Las franjas de un eje no bloquean al otro.
    """
    if work_kind == "tatuaje":
        return "tattoo"
    return "piercing"


def work_kind_infer_from_existing_row(row: Dict[str, Any]) -> str:
    """Heurística desde fila API (tipo de servicio + detalle) para edición rápida desde calendario."""
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


__all__ = [
    "BOOKING_WORK_KIND_META",
    "BOOKING_WORK_KIND_ORDER",
    "service_and_detail_for_work_kind",
    "work_kind_infer_from_existing_row",
    "work_kind_to_assignee_role",
    "work_kind_to_schedule_kind",
]
