"""Esquemas Pydantic: firma de contratos."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

from app.domain.models import ContractSign


def _is_non_empty_signature_blob(value: Optional[str]) -> bool:
    """Firma enviada desde el panel: imagen data URL o texto del fallback del lienzo."""
    if value is None:
        return False
    v = str(value).strip()
    if len(v) < 80:
        return False
    if v.startswith("data:image/"):
        parts = v.split(",", 1)
        return len(parts) == 2 and len(parts[1].strip()) >= 40
    return len(v) >= 4


def _is_document_capture(value: Optional[str]) -> bool:
    if value is None:
        return False
    v = str(value).strip()
    return len(v) >= 80 and v.startswith("data:image/")


class ContractSignRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    appointment_id: int = Field(..., ge=1)
    is_minor: bool = False
    health_data: dict[str, JsonValue]
    signature: str = Field(..., min_length=1, max_length=1_000_000)
    tutor_signature: Optional[str] = Field(None, max_length=1_000_000)
    artist_signature: Optional[str] = Field(None, max_length=1_000_000)
    tutor_document_front: Optional[str] = None
    tutor_document_back: Optional[str] = None
    contract_text: Optional[str] = None
    template_id: Optional[int] = Field(None, ge=1)

    @field_validator("health_data")
    @classmethod
    def health_not_empty(cls, v: dict[str, JsonValue]) -> dict[str, JsonValue]:
        if not v:
            raise ValueError("health_data must not be empty")
        return v

    @model_validator(mode="after")
    def signatures_and_minor_documents(self) -> ContractSignRequest:
        if not _is_non_empty_signature_blob(self.signature):
            raise ValueError(
                "La firma del cliente es obligatoria: debe dibujarse en el recuadro (o completarse en modo texto si aplica)."
            )
        if not _is_non_empty_signature_blob(self.artist_signature):
            raise ValueError("La firma del tatuador o perforador es obligatoria.")
        if self.is_minor:
            if not _is_non_empty_signature_blob(self.tutor_signature):
                raise ValueError("La firma del tutor o representante es obligatoria para menores de edad.")
            if not _is_document_capture(self.tutor_document_front):
                raise ValueError("Debes adjuntar la foto del anverso del documento del tutor.")
            if not _is_document_capture(self.tutor_document_back):
                raise ValueError("Debes adjuntar la foto del reverso del documento del tutor.")
        return self


def contract_sign_to_domain(req: ContractSignRequest) -> ContractSign:
    return ContractSign(
        appointment_id=req.appointment_id,
        is_minor=req.is_minor,
        health_data=req.health_data,
        signature=req.signature,
        tutor_signature=req.tutor_signature,
        artist_signature=req.artist_signature,
        tutor_document_front=req.tutor_document_front,
        tutor_document_back=req.tutor_document_back,
        contract_text=req.contract_text,
        template_id=req.template_id,
    )
