"""Validación de formularios antes de llamar a la API."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.customer import SOCIAL_MEDIA_MAX_LEN
from pydantic import EmailStr, TypeAdapter

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME_FULL = re.compile(
    r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?$"
)
_VERSION_RE = re.compile(r"^\d+\.\d+(\.\d+)?$")


def normalize_phone_digits(phone: str) -> str:
    """Solo dígitos, para validar longitud de celular (ej. CO: 10)."""
    return "".join(c for c in str(phone or "") if c.isdigit())


def mobile_phone_co_10_error(phone: str) -> Optional[str]:
    """
    Celular Colombia: exactamente 10 dígitos (se ignoran espacios, +, guiones en el conteo).
    """
    if len(normalize_phone_digits(phone)) != 10:
        return "El celular debe tener exactamente 10 dígitos."
    return None


def optional_mobile_phone_co_10_error(phone: Optional[str]) -> Optional[str]:
    """Igual que mobile_phone_co_10_error si hay texto; vacío permite omitir."""
    if not (phone or "").strip():
        return None
    return mobile_phone_co_10_error(phone)


def social_media_text_error(raw: str, *, max_len: int = SOCIAL_MEDIA_MAX_LEN) -> Optional[str]:
    """Validación para redes como texto plano."""
    s = (raw or "").strip()
    if not s:
        return None
    if len(s) > max_len:
        return f"Redes sociales: como máximo {max_len} caracteres."
    return None


# Alias por compatibilidad con imports antiguos.
def social_media_json_handle_error(raw: str) -> Optional[str]:
    return social_media_text_error(raw)


@dataclass
class FieldError:
    field: str
    message: str


def _err(errors: List[FieldError], field: str, message: str) -> None:
    errors.append(FieldError(field=field, message=message))


def validate_appointment(
    name: str,
    phone: str,
    email: str,
    service: str,
    date_str: str,
    detail: str,
    deposit: float,
) -> Tuple[bool, List[FieldError]]:
    errors: List[FieldError] = []
    name = (name or "").strip()
    phone = (phone or "").strip()
    email = (email or "").strip()
    service = (service or "").strip()
    date_str = (date_str or "").strip()

    if len(name) < 2:
        _err(errors, "name", "El nombre debe tener al menos 2 caracteres.")
    ph_err = mobile_phone_co_10_error(phone)
    if ph_err:
        _err(errors, "phone", ph_err)
    if not email:
        _err(errors, "email", "El correo electrónico es obligatorio.")
    else:
        try:
            TypeAdapter(EmailStr).validate_python(email)
        except Exception:
            _err(errors, "email", "Introduce un correo electrónico válido.")
    if not service:
        _err(errors, "service", "Indica el tipo de servicio.")
    elif len(service) < 2:
        _err(errors, "service", "Describe el servicio (mínimo 2 caracteres).")
    date_str_clean = date_str.strip()
    if not _DATETIME_FULL.match(date_str_clean.replace("T", " ")):
        _err(errors, "date", "La fecha/hora debe ser AAAA-MM-DD o AAAA-MM-DD HH:MM.")
    else:
        try:
            from app.schemas.appointment import normalize_appointment_datetime_string

            normalize_appointment_datetime_string(date_str_clean)
        except ValueError as e:
            _err(errors, "date", str(e))
    if deposit < 0:
        _err(errors, "deposit", "El depósito no puede ser negativo.")

    return (len(errors) == 0, errors)


def validate_survey(
    appointment_id: int,
    rating: int,
    comments: str,
) -> Tuple[bool, List[FieldError]]:
    errors: List[FieldError] = []
    if appointment_id <= 0:
        _err(errors, "appointment_id", "El ID de cita debe ser un entero positivo.")
    if rating < 1 or rating > 5:
        _err(errors, "rating", "La calificación debe estar entre 1 y 5.")
    if comments and len(comments) > 2000:
        _err(errors, "comments", "Los comentarios no pueden superar 2000 caracteres.")
    return (len(errors) == 0, errors)


def validate_contract(
    appointment_id: int,
    signature: str,
    health_json: str,
    tutor_signature: str,
    template_id: Optional[int],
) -> Tuple[bool, List[FieldError], Optional[Dict[str, Any]]]:
    errors: List[FieldError] = []
    health: Optional[Dict[str, Any]] = None

    if appointment_id <= 0:
        _err(errors, "appointment_id", "El ID de cita debe ser un entero positivo.")
    sig = (signature or "").strip()
    if len(sig) < 3:
        _err(errors, "signature", "La firma o identificador debe tener al menos 3 caracteres.")

    raw = (health_json or "").strip()
    if not raw:
        _err(errors, "health_data", "Los datos de salud (JSON) son obligatorios.")
    else:
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                _err(errors, "health_data", "El JSON de salud debe ser un objeto { ... }.")
            else:
                health = parsed
        except json.JSONDecodeError as e:
            _err(errors, "health_data", f"JSON inválido: {e.msg}")

    if template_id is not None and template_id <= 0:
        _err(errors, "template_id", "Si indicas plantilla, el ID debe ser positivo.")

    tutor = (tutor_signature or "").strip()
    # tutor opcional; si se rellena, mínimo longitud
    if tutor and len(tutor) < 3:
        _err(errors, "tutor_signature", "La firma del tutor debe tener al menos 3 caracteres o dejarse vacía.")

    return (len(errors) == 0, errors, health)


def validate_template(
    name: str,
    version: str,
    content: str,
    is_active: bool,
) -> Tuple[bool, List[FieldError]]:
    errors: List[FieldError] = []
    name = (name or "").strip()
    version = (version or "").strip()
    content = (content or "").strip()

    if len(name) < 2:
        _err(errors, "name", "El nombre de la plantilla debe tener al menos 2 caracteres.")
    if not _VERSION_RE.match(version):
        _err(errors, "version", "Usa un formato de versión tipo 1.0 o 1.0.2.")
    if len(content) < 10:
        _err(errors, "content", "El contenido legal debe tener al menos 10 caracteres.")

    return (len(errors) == 0, errors)


def validate_template_id(template_id: int) -> Tuple[bool, List[FieldError]]:
    errors: List[FieldError] = []
    if template_id <= 0:
        _err(errors, "template_id", "El ID de plantilla debe ser un entero positivo.")
    return (len(errors) == 0, errors)


def validate_report_dates(start: str, end: str) -> Tuple[bool, List[FieldError]]:
    errors: List[FieldError] = []
    start = (start or "").strip()
    end = (end or "").strip()
    for label, val in (("start_date", start), ("end_date", end)):
        if not _DATE_RE.match(val):
            _err(errors, label, "Usa formato AAAA-MM-DD.")
        else:
            try:
                datetime.strptime(val, "%Y-%m-%d")
            except ValueError:
                _err(errors, label, "Fecha no válida.")
    if not errors and start and end:
        if datetime.strptime(start, "%Y-%m-%d") > datetime.strptime(end, "%Y-%m-%d"):
            _err(errors, "end_date", "La fecha fin debe ser posterior o igual al inicio.")
    return (len(errors) == 0, errors)
