"""Etiqueta de trabajo realizado para reportes (perforación vs tipo de cita)."""

from __future__ import annotations

import json
from typing import Any, Mapping, Optional

from app.domain.booking_work_kind import booking_work_kind_label
from app.domain.contract_kinds import appointment_to_contract_kind
from app.domain.piercing_procedure_labels import (
    infer_piercing_type_from_detail,
    piercing_type_display_label,
    resolve_piercing_type_canonical,
)
from app.domain.procedure_consent import PROCEDURE_CONSENT_SURVEY_QUESTION_ID

# Reutiliza la misma pregunta que el consentimiento de piercing (select de tipo de perforación).
PIERCING_TYPE_SURVEY_QUESTION_ID = PROCEDURE_CONSENT_SURVEY_QUESTION_ID


def normalize_survey_answer_display(raw: Any) -> Optional[str]:
    """Texto legible desde answer_text (opción única o JSON de checkbox)."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if s.startswith("[") or s.startswith("{"):
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list) and parsed:
                first = str(parsed[0]).strip()
                return first or None
            if isinstance(parsed, dict):
                for key in ("value", "label", "text"):
                    if key in parsed and str(parsed[key]).strip():
                        return str(parsed[key]).strip()
        except json.JSONDecodeError:
            pass
    return s


def work_performed_label(
    row: Mapping[str, Any],
    *,
    piercing_survey_by_appointment: Optional[Mapping[int, str]] = None,
    piercing_type_index: Optional[Mapping[str, str]] = None,
) -> str:
    """
    Columna de reporte financiero:
    - Cita de piercing: tipo de perforación (Helix, Lóbulo, Nostril…) si hay encuesta o detalle.
    - Si no: tipo de trabajo inferido (tatuaje, limpieza, cambio, etc.).
    """
    if appointment_to_contract_kind(row) == "tattoo":
        return booking_work_kind_label(row)

    idx = dict(piercing_type_index or {})
    aid_raw = row.get("id")
    try:
        aid = int(aid_raw or 0)
    except (TypeError, ValueError):
        aid = 0
    if piercing_survey_by_appointment and aid > 0:
        hit = piercing_survey_by_appointment.get(aid)
        if hit and str(hit).strip():
            return str(hit).strip()

    if idx:
        from_detail = infer_piercing_type_from_detail(str(row.get("detail") or ""), idx)
        if from_detail:
            return piercing_type_display_label(from_detail)

    return booking_work_kind_label(row)


def resolve_work_performed_from_survey_raw(
    raw_answer: Optional[str],
    piercing_type_index: Mapping[str, str],
) -> Optional[str]:
    """Normaliza respuesta de encuesta al catálogo y devuelve etiqueta para reporte."""
    norm = normalize_survey_answer_display(raw_answer)
    canonical = resolve_piercing_type_canonical(norm, dict(piercing_type_index))
    if not canonical:
        canonical = resolve_piercing_type_canonical(str(raw_answer or ""), dict(piercing_type_index))
    if canonical:
        return piercing_type_display_label(canonical)
    return norm.strip() if norm else None


__all__ = [
    "PIERCING_TYPE_SURVEY_QUESTION_ID",
    "booking_work_kind_label",
    "normalize_survey_answer_display",
    "resolve_work_performed_from_survey_raw",
    "work_performed_label",
]
