"""Validación de formularios antes de llamar a la API."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PHONE_RE = re.compile(r"^[\d\s+\-().]{7,20}$")
_VERSION_RE = re.compile(r"^\d+\.\d+(\.\d+)?$")


@dataclass
class FieldError:
    field: str
    message: str


def _err(errors: List[FieldError], field: str, message: str) -> None:
    errors.append(FieldError(field=field, message=message))


def validate_appointment(
    name: str,
    phone: str,
    service: str,
    date_str: str,
    detail: str,
    deposit: float,
) -> Tuple[bool, List[FieldError]]:
    errors: List[FieldError] = []
    name = (name or "").strip()
    phone = (phone or "").strip()
    service = (service or "").strip()
    date_str = (date_str or "").strip()

    if len(name) < 2:
        _err(errors, "name", "El nombre debe tener al menos 2 caracteres.")
    if not _PHONE_RE.match(phone):
        _err(errors, "phone", "Introduce un teléfono válido (7–20 dígitos o símbolos + - espacio).")
    if not service:
        _err(errors, "service", "Indica el tipo de servicio.")
    elif len(service) < 2:
        _err(errors, "service", "Describe el servicio (mínimo 2 caracteres).")
    if not _DATE_RE.match(date_str):
        _err(errors, "date", "La fecha debe tener formato AAAA-MM-DD.")
    else:
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            _err(errors, "date", "La fecha no es válida en el calendario.")
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
