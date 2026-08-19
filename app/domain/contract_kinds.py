"""Tipos de plantilla de contrato (tatuaje, piercing, recibo) y mapeo desde cita."""
from __future__ import annotations

from typing import Any, Literal, Mapping

from app.domain.service_types import configured_service_types

ContractKind = Literal["tattoo", "piercing", "recibo"]

# Kinds usados al firmar citas (no incluye recibo: va a órdenes de abono).
SigningContractKind = Literal["tattoo", "piercing"]

KIND_LABEL_ES: dict[ContractKind, str] = {
    "tattoo": "Tatuaje",
    "piercing": "Piercing",
    "recibo": "Recibo",
}

"""Ámbito de una pregunta de encuesta (puede ser solo tatuaje, solo piercing, o ambos)."""
SurveyQuestionScope = Literal["tattoo", "piercing", "both"]

SCOPE_LABEL_ES: dict[SurveyQuestionScope, str] = {
    "tattoo": "Tatuaje",
    "piercing": "Piercing",
    "both": "Ambas (tatuaje y piercing)",
}

_NO_CONTRACT_CANONICAL = frozenset({"cambio", "limpieza"})
_NO_CONTRACT_WORK_KINDS = frozenset({"limpieza_piercing", "cambio_piercing"})


def service_type_requires_contract(service_type: str | None) -> bool:
    """
    Solo **Cambio** y **Limpieza** (coincidencia sin distinguir mayúsculas, o como
    aparezcan en `SERVICE_TYPE_ENUM_VALUES`) no requieren firma de contrato.
    """
    key = (service_type or "").strip().lower()
    if not key:
        return True
    if key in _NO_CONTRACT_CANONICAL:
        return False
    for label in configured_service_types():
        lk = label.strip().lower()
        if lk == key:
            return lk not in _NO_CONTRACT_CANONICAL
    return True


def _appointment_detail_value(appointment: Any) -> str:
    if appointment is None:
        return ""
    if isinstance(appointment, Mapping):
        return str(appointment.get("detail") or "")
    return str(getattr(appointment, "detail", None) or "")


def appointment_requires_contract(appointment: Any) -> bool:
    """
    Firma/envío de contrato: no aplica a Limpieza ni Cambio (tipo de servicio o
    etiquetas legacy en el detalle cuando la cita quedó guardada como Piercing).
    """
    from app.domain.booking_work_kind import work_kind_infer_from_existing_row

    if appointment is None:
        return True
    if isinstance(appointment, Mapping):
        kind = work_kind_infer_from_existing_row(appointment)
    else:
        kind = work_kind_infer_from_existing_row(
            {
                "service_type": _appointment_service_type_value(appointment),
                "service": _appointment_service_type_value(appointment),
                "detail": _appointment_detail_value(appointment),
            }
        )
    if kind in _NO_CONTRACT_WORK_KINDS:
        return False
    return service_type_requires_contract(_appointment_service_type_value(appointment))


def service_type_to_contract_kind(service_type: str | None) -> SigningContractKind:
    """Mapeo para citas con contrato: Tatuaje → tattoo; resto aplicable → piercing."""
    s = (service_type or "").strip().lower()
    if "tatu" in s or s == "tattoo":
        return "tattoo"
    return "piercing"


def _appointment_service_type_value(appointment: Any) -> str:
    """Tipo de servicio de una cita como dict o como objeto (p. ej. SimpleNamespace de `get_by_id`)."""
    if appointment is None:
        return ""
    if isinstance(appointment, Mapping):
        return str(appointment.get("service_type") or appointment.get("service") or "")
    st = getattr(appointment, "service_type", None)
    if st is not None and str(st).strip():
        return str(st)
    return str(getattr(appointment, "service", None) or "")


def appointment_to_contract_kind(appointment: Any) -> SigningContractKind:
    """Elige plantilla activa según tipo de servicio de la cita (solo si aplica contrato)."""
    return service_type_to_contract_kind(_appointment_service_type_value(appointment))


def service_type_to_assignee_panel_role(service_type: str | None) -> str:
    """
    Rol en `panel_users` que debe tener el profesional asignado a la cita.
    Tatuaje → tatuador; el resto de servicios aplicables → perforador.
    """
    return "tatuador" if service_type_to_contract_kind(service_type) == "tattoo" else "perforador"
