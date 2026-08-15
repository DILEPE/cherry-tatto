"""Payload JSON hacia n8n `treatment-sent` (recordatorio de cuidados tras firmar contrato)."""
from __future__ import annotations

from typing import Any, Mapping, Optional


def phone_digits_international(raw: str | None) -> str:
    """Dígitos en formato internacional sin +. Móvil CO de 10 dígitos → prefijo 57."""
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    if len(digits) == 10 and digits.startswith("3"):
        return f"57{digits}"
    return digits


def treatment_sent_service_type(contract_kind: str) -> str:
    """Valores que espera n8n: piercing | tatuaje."""
    return "tatuaje" if contract_kind == "tattoo" else "piercing"


def build_treatment_sent_payload(
    *,
    customer_id: int,
    customer_name: str,
    phone: str,
    service_type: str,
    service_date: str,
) -> dict[str, object]:
    return {
        "customer_id": int(customer_id),
        "customer_name": (customer_name or "").strip(),
        "phone": phone_digits_international(phone),
        "service_type": service_type,
        "service_date": (service_date or "").strip(),
    }


def customer_display_name(row: Mapping[str, Any] | None) -> str:
    if not row:
        return ""
    first = str(row.get("first_name") or "").strip()
    last = str(row.get("last_name") or "").strip()
    return " ".join(p for p in (first, last) if p)


def treatment_sent_payload_from_appointment(
    appointment: Any,
    *,
    customer_row: Optional[Mapping[str, Any]] = None,
    contract_kind: str,
) -> Optional[dict[str, object]]:
    """Arma el JSON plano del webhook. None si falta cliente o teléfono."""
    raw_id = getattr(appointment, "customer_id", None)
    try:
        customer_id = int(raw_id) if raw_id is not None else 0
    except (TypeError, ValueError):
        customer_id = 0
    if customer_id <= 0:
        return None

    name = str(getattr(appointment, "name", "") or "").strip()
    if customer_row:
        from_customer = customer_display_name(customer_row)
        if from_customer:
            name = from_customer

    phone = str(getattr(appointment, "phone", "") or "").strip()
    if customer_row:
        cust_phone = str(customer_row.get("phone_number") or "").strip()
        if cust_phone:
            phone = cust_phone

    payload = build_treatment_sent_payload(
        customer_id=customer_id,
        customer_name=name,
        phone=phone,
        service_type=treatment_sent_service_type(contract_kind),
        service_date=str(getattr(appointment, "date", "") or ""),
    )
    if not payload["phone"]:
        return None
    return payload
