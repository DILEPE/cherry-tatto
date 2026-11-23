"""Celulares de cliente para ficha y WhatsApp.

Colombia se guarda en 10 dígitos (empiezan por 3). Otro país se guarda con
indicativo, de 11 a 15 dígitos, sin el signo +.
"""
from __future__ import annotations

WHATSAPP_PHONE_ERROR = (
    "Celular de Colombia: 10 dígitos que empiecen por 3. "
    "Otro país: indicativo y número, de 11 a 15 dígitos."
)


def digits_only(raw: str | None) -> str:
    return "".join(ch for ch in (raw or "") if ch.isdigit())


def is_whatsapp_phone(digits: str) -> bool:
    if len(digits) == 10 and digits.startswith("3"):
        return True
    return 11 <= len(digits) <= 15


def normalize_customer_phone(raw: str | None, *, required: bool) -> str | None:
    """Deja solo dígitos. Vacío opcional → None. Formato inválido → ValueError."""
    digits = digits_only(raw)
    if not digits:
        if required:
            raise ValueError(WHATSAPP_PHONE_ERROR)
        return None
    if not is_whatsapp_phone(digits):
        raise ValueError(WHATSAPP_PHONE_ERROR)
    return digits


def phone_digits_international(raw: str | None) -> str:
    """Dígitos para WhatsApp, sin +. Móvil CO de 10 dígitos → prefijo 57.

    Si el número ya trae indicativo (11 a 15 dígitos, incluido 57…), se deja igual.
    """
    digits = digits_only(raw)
    if len(digits) == 10 and digits.startswith("3"):
        return f"57{digits}"
    return digits
