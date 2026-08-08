"""Esquemas: documentos PDF de consentimiento / tipos de piercing."""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# PDF ~8 MiB en binario ≈ 11 MiB en base64.
_MAX_PDF_BASE64_CHARS = 12_000_000


def _validate_pdf_base64(raw: str) -> str:
    s = (raw or "").strip()
    # Por si llega el data-URL completo desde el front.
    if "base64," in s:
        s = s.split("base64,", 1)[1].strip()
    s = "".join(s.split())  # quita saltos/espacios del base64
    if not s:
        raise ValueError("El PDF en base64 es obligatorio")
    if len(s) > _MAX_PDF_BASE64_CHARS:
        raise ValueError("El PDF es demasiado grande (máx. ~8 MB)")
    try:
        # `standard_b64decode(..., validate=)` no existe en Python < 3.11.
        data = base64.b64decode(s, validate=False)
    except (binascii.Error, ValueError) as e:
        raise ValueError("El PDF no es un Base64 válido") from e
    # Algunos PDF traen BOM / basura mínima al inicio.
    head = data.lstrip()[:8]
    if len(data) < 5 or not head.startswith(b"%PDF"):
        raise ValueError("El archivo no parece un PDF válido")
    return s


class ProcedureConsentCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    survey_option_label: str = Field(..., min_length=1, max_length=191)
    source_filename: str = Field(..., min_length=1, max_length=255)
    pdf_base64: str = Field(..., min_length=8)

    @field_validator("survey_option_label")
    @classmethod
    def normalize_label(cls, v: str) -> str:
        t = (v or "").strip()
        if not t:
            raise ValueError("El nombre del tipo es obligatorio")
        return t

    @field_validator("source_filename")
    @classmethod
    def normalize_filename(cls, v: str) -> str:
        t = (v or "").strip()
        if not t.lower().endswith(".pdf"):
            t = f"{t}.pdf"
        return t[:255]

    @field_validator("pdf_base64")
    @classmethod
    def check_pdf(cls, v: str) -> str:
        return _validate_pdf_base64(v)


class ProcedureConsentUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    survey_option_label: Optional[str] = Field(None, min_length=1, max_length=191)
    source_filename: Optional[str] = Field(None, min_length=1, max_length=255)
    pdf_base64: Optional[str] = Field(None, min_length=8)

    @field_validator("survey_option_label")
    @classmethod
    def normalize_label(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        t = v.strip()
        return t or None

    @field_validator("source_filename")
    @classmethod
    def normalize_filename(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        t = v.strip()
        if not t:
            return None
        if not t.lower().endswith(".pdf"):
            t = f"{t}.pdf"
        return t[:255]

    @field_validator("pdf_base64")
    @classmethod
    def check_pdf(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not str(v).strip():
            return None
        return _validate_pdf_base64(v)

    @model_validator(mode="after")
    def at_least_one_change(self) -> ProcedureConsentUpdate:
        if (
            self.survey_option_label is None
            and self.source_filename is None
            and self.pdf_base64 is None
        ):
            raise ValueError("Indica al menos un campo a actualizar")
        return self


class ProcedureConsentListItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    survey_option_label: str
    source_filename: str
    updated_at: Optional[datetime] = None
    pdf_bytes: int = 0
    is_tattoo: bool = False


class ProcedureConsentDetail(ProcedureConsentListItem):
    pdf_base64: str


class ProcedureConsentCreatedResponse(BaseModel):
    status: str = "success"
    message: str
    survey_option_label: str
