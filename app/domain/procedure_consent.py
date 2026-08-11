"""Consentimientos PDF por procedimiento (encuesta de firma → envío a n8n)."""

from __future__ import annotations

from app.domain.piercing_procedure_labels import piercing_type_display_label

# Pregunta de encuesta cuya respuesta elige el PDF de piercing (en tatuaje se fuerza «Tatuaje»).
PROCEDURE_CONSENT_SURVEY_QUESTION_ID: int = 3


def care_instructions_pdf_filename(*, contract_kind: str, procedure_label: str) -> str:
    """
    Nombre del archivo al enviar cuidados por n8n/WhatsApp.

    - Tatuaje → ``Cuidados para tatuajes.pdf``
    - Piercing → ``Cuidados para piercing {tipo anatómico}.pdf``
    """
    kind = (contract_kind or "").strip().lower()
    if kind == "tattoo":
        return "Cuidados para tatuajes.pdf"

    display = piercing_type_display_label(procedure_label)
    if not display or display == "—":
        display = (procedure_label or "").strip() or "piercing"
    safe = (
        display.replace("/", "-")
        .replace("\\", "-")
        .replace("\0", "")
        .replace('"', "")
        .strip()
    )
    return f"Cuidados para piercing {safe}.pdf"
