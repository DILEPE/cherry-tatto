"""Pydantic schemas for customer API validation."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

DocumentType = Literal["CC", "TI", "CE", "PAS"]

# Redes / contacto social en BD: VARCHAR, texto plano.
SOCIAL_MEDIA_MAX_LEN = 50

# Fecha reservada para “nacimiento pendiente” al agendar sin capturar cumpleaños.
# Sustituir por la fecha real en gestión de clientes o en la etapa 1 de firma de contrato.
CUSTOMER_BIRTH_PENDING = date(2001, 7, 13)
CUSTOMER_BIRTH_PENDING_ISO: str = CUSTOMER_BIRTH_PENDING.isoformat()

# Textos para OpenAPI (esquemas Pydantic / Litestar).
BIRTH_DATE_FIELD_DESCRIPTION = (
    "Fecha de nacimiento real del cliente (AAAA-MM-DD). "
    f"Sentinela interna para “nacimiento pendiente” (alta solo al agendar sin cumpleaños): `{CUSTOMER_BIRTH_PENDING_ISO}`. "
    "Si envías esa fecha: `is_minor` debe ser `false` y no incluyas `document_issue_date`; permite `document_type` TI sin validar edad. "
    "Sustituye el sentinela por la fecha real con `PUT /api/customers/{{id}}` o en la app (firma de contrato). "
    "No usar el valor sentinela como fecha de nacimiento real de una persona."
)
IS_MINOR_FIELD_DESCRIPTION = (
    "Debe coincidir con la edad derivada de `birth_date` (menor de 18 años). "
    f"Mientras `birth_date` sea el sentinela de pendiente (`{CUSTOMER_BIRTH_PENDING_ISO}`), debe ser `false`."
)
DOCUMENT_ISSUE_CLIENT_DESCRIPTION = (
    "Expedición del documento del cliente. "
    f"No enviar si `birth_date` es el sentinela de pendiente (`{CUSTOMER_BIRTH_PENDING_ISO}`)."
)
_SOCIAL_MEDIA_DESCRIPTION = (
    f"Texto plano (redes o contacto), máximo {SOCIAL_MEDIA_MAX_LEN} caracteres. No es JSON."
)
CUSTOMER_EMBEDDED_IN_APPOINTMENT_DESCRIPTION = (
    "Objeto para crear el cliente al mismo tiempo que la cita (excluyente con `customer_id` si ya existe). "
    f"Si aún no se conoce el cumpleaños: enviar `birth_date=\"{CUSTOMER_BIRTH_PENDING_ISO}\"`, `is_minor=false`, "
    "sin `document_issue_date`; `document_type` puede ser TI u otros. Completar datos reales después vía `PUT /api/customers/{{id}}`."
)


class CustomerCreate(BaseModel):
    """Alta de cliente. Ver `birth_date` para el flujo de nacimiento pendiente en agendamiento."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    birth_date: date = Field(..., description=BIRTH_DATE_FIELD_DESCRIPTION)
    document_type: DocumentType = Field(
        ...,
        description="CC, TI, CE o PAS. Con nacimiento pendiente (sentinela) se admite TI sin comprobar mayoría de edad.",
    )
    document_number: str = Field(..., min_length=5, max_length=32)
    document_issue_date: Optional[date] = Field(default=None, description=DOCUMENT_ISSUE_CLIENT_DESCRIPTION)
    email: EmailStr
    phone_number: str = Field(..., min_length=7, max_length=32)
    address: Optional[str] = Field(None, max_length=500)
    nationality: Optional[str] = Field(None, max_length=100)
    profession: Optional[str] = Field(None, max_length=150)
    social_media: Optional[str] = Field(
        default=None,
        max_length=SOCIAL_MEDIA_MAX_LEN,
        description=_SOCIAL_MEDIA_DESCRIPTION,
    )
    emergency_contact_name: Optional[str] = Field(None, max_length=150)
    emergency_contact_phone: Optional[str] = Field(None, max_length=32)
    is_minor: bool = Field(default=False, description=IS_MINOR_FIELD_DESCRIPTION)
    guardian_name: Optional[str] = Field(None, max_length=200)
    guardian_document_type: Optional[DocumentType] = None
    guardian_document_number: Optional[str] = Field(None, max_length=32)
    guardian_document_issue_date: Optional[date] = None

    @field_validator("social_media", mode="before")
    @classmethod
    def _social_media_empty_string(cls, v: object) -> object:
        if v == "":
            return None
        return v

    @staticmethod
    def _subtract_years(base: date, years: int) -> date:
        year = base.year - years
        try:
            return base.replace(year=year)
        except ValueError:
            # Ajuste para 29/02 en años no bisiestos
            return base.replace(year=year, day=28)

    @staticmethod
    def _full_years_between(start: date, end: date) -> int:
        return end.year - start.year - ((end.month, end.day) < (start.month, start.day))

    @staticmethod
    def _is_minor_by_birth_date(birth_date: date) -> bool:
        today = date.today()
        years = CustomerCreate._full_years_between(birth_date, today)
        return years < 18

    @model_validator(mode="after")
    def guardian_if_minor(self) -> "CustomerCreate":
        today = date.today()
        min_allowed_date = self._subtract_years(today, 100)

        if self.birth_date == CUSTOMER_BIRTH_PENDING:
            if bool(self.is_minor):
                raise ValueError(
                    "Con fecha de nacimiento pendiente (agendamiento), is_minor debe ser false; "
                    "se recalculará al completar la fecha real."
                )
            if self.document_issue_date is not None:
                raise ValueError(
                    "No indiques fecha de expedición del documento mientras el nacimiento sigue pendiente."
                )
            # Permite TI u otros tipos sin verificar edad ni tutor hasta completar datos.
            return self

        if self.birth_date < min_allowed_date or self.birth_date > today:
            raise ValueError("birth_date must be within the last 100 years and not in the future.")
        if self.document_issue_date is not None and (
            self.document_issue_date < min_allowed_date or self.document_issue_date > today
        ):
            raise ValueError("document_issue_date must be within the last 100 years and not in the future.")

        expected_minor = self._is_minor_by_birth_date(self.birth_date)
        if bool(self.is_minor) != expected_minor:
            raise ValueError("is_minor must match birth_date (under 18 years old).")

        if self.document_type == "TI":
            if not expected_minor:
                raise ValueError("document_type TI requires customer under 18.")
            if self.document_issue_date is not None and self.document_issue_date > today:
                raise ValueError("document_issue_date cannot be in the future for TI.")
        else:
            if self.document_issue_date is not None and not expected_minor:
                adulthood_date = self._subtract_years(self.birth_date, -18)
                if self.document_issue_date < adulthood_date:
                    raise ValueError(
                        "For non-TI documents, document_issue_date must be at least 18 years after birth_date."
                    )

        # Menores: el tutor puede completarse después del agendamiento (p. ej. en administración de clientes).
        if self.is_minor and self.guardian_document_type == "TI":
            raise ValueError("guardian_document_type cannot be TI.")
        if self.is_minor and self.guardian_document_issue_date is not None:
            if self.guardian_document_issue_date < min_allowed_date or self.guardian_document_issue_date > today:
                raise ValueError(
                    "guardian_document_issue_date must be within the last 100 years and not in the future."
                )
            if self._full_years_between(self.guardian_document_issue_date, today) < 18:
                raise ValueError(
                    "guardian_document_issue_date must be at least 18 years before current date."
                )
        return self


class CustomerUpdate(BaseModel):
    """Actualización de cliente. Mismas reglas que en creación para el sentinela de `birth_date`."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    birth_date: date = Field(..., description=BIRTH_DATE_FIELD_DESCRIPTION)
    document_type: DocumentType = Field(
        ...,
        description="CC, TI, CE o PAS. Con nacimiento pendiente (sentinela) se admite TI sin comprobar mayoría de edad.",
    )
    document_number: str = Field(..., min_length=5, max_length=32)
    document_issue_date: Optional[date] = Field(default=None, description=DOCUMENT_ISSUE_CLIENT_DESCRIPTION)
    email: EmailStr
    phone_number: str = Field(..., min_length=7, max_length=32)
    address: Optional[str] = Field(None, max_length=500)
    nationality: Optional[str] = Field(None, max_length=100)
    profession: Optional[str] = Field(None, max_length=150)
    social_media: Optional[str] = Field(
        default=None,
        max_length=SOCIAL_MEDIA_MAX_LEN,
        description=_SOCIAL_MEDIA_DESCRIPTION,
    )
    emergency_contact_name: Optional[str] = Field(None, max_length=150)
    emergency_contact_phone: Optional[str] = Field(None, max_length=32)
    is_minor: bool = Field(default=False, description=IS_MINOR_FIELD_DESCRIPTION)
    guardian_name: Optional[str] = Field(None, max_length=200)
    guardian_document_type: Optional[DocumentType] = None
    guardian_document_number: Optional[str] = Field(None, max_length=32)
    guardian_document_issue_date: Optional[date] = None

    @field_validator("social_media", mode="before")
    @classmethod
    def _social_media_empty_string_u(cls, v: object) -> object:
        if v == "":
            return None
        return v

    @staticmethod
    def _subtract_years(base: date, years: int) -> date:
        year = base.year - years
        try:
            return base.replace(year=year)
        except ValueError:
            return base.replace(year=year, day=28)

    @staticmethod
    def _full_years_between(start: date, end: date) -> int:
        return end.year - start.year - ((end.month, end.day) < (start.month, start.day))

    @staticmethod
    def _is_minor_by_birth_date(birth_date: date) -> bool:
        today = date.today()
        years = CustomerUpdate._full_years_between(birth_date, today)
        return years < 18

    @model_validator(mode="after")
    def guardian_if_minor(self) -> "CustomerUpdate":
        today = date.today()
        min_allowed_date = self._subtract_years(today, 100)

        if self.birth_date == CUSTOMER_BIRTH_PENDING:
            if bool(self.is_minor):
                raise ValueError(
                    "Con fecha de nacimiento pendiente, is_minor debe ser false hasta completar la fecha real."
                )
            if self.document_issue_date is not None:
                raise ValueError(
                    "No indiques fecha de expedición del documento mientras el nacimiento sigue pendiente."
                )
            return self

        if self.birth_date < min_allowed_date or self.birth_date > today:
            raise ValueError("birth_date must be within the last 100 years and not in the future.")
        if self.document_issue_date is not None and (
            self.document_issue_date < min_allowed_date or self.document_issue_date > today
        ):
            raise ValueError("document_issue_date must be within the last 100 years and not in the future.")

        expected_minor = self._is_minor_by_birth_date(self.birth_date)
        if bool(self.is_minor) != expected_minor:
            raise ValueError("is_minor must match birth_date (under 18 years old).")

        if self.document_type == "TI":
            if not expected_minor:
                raise ValueError("document_type TI requires customer under 18.")
            if self.document_issue_date is not None and self.document_issue_date > today:
                raise ValueError("document_issue_date cannot be in the future for TI.")
        else:
            if self.document_issue_date is not None and not expected_minor:
                adulthood_date = self._subtract_years(self.birth_date, -18)
                if self.document_issue_date < adulthood_date:
                    raise ValueError(
                        "For non-TI documents, document_issue_date must be at least 18 years after birth_date."
                    )

        if self.is_minor and self.guardian_document_type == "TI":
            raise ValueError("guardian_document_type cannot be TI.")
        if self.is_minor and self.guardian_document_issue_date is not None:
            if self.guardian_document_issue_date < min_allowed_date or self.guardian_document_issue_date > today:
                raise ValueError(
                    "guardian_document_issue_date must be within the last 100 years and not in the future."
                )
            if self._full_years_between(self.guardian_document_issue_date, today) < 18:
                raise ValueError(
                    "guardian_document_issue_date must be at least 18 years before current date."
                )
        return self


class CustomerPublic(BaseModel):
    """Cliente en respuestas GET. `birth_date` puede ser el sentinela de pendiente hasta completar ficha."""

    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: int
    first_name: str
    last_name: str
    birth_date: date = Field(description=BIRTH_DATE_FIELD_DESCRIPTION)
    document_type: str
    document_number: str
    document_issue_date: Optional[date] = None
    email: str
    phone_number: str
    address: Optional[str] = None
    nationality: Optional[str] = None
    profession: Optional[str] = None
    social_media: Optional[str] = Field(
        default=None,
        max_length=SOCIAL_MEDIA_MAX_LEN,
        description=_SOCIAL_MEDIA_DESCRIPTION,
    )
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    is_minor: bool = Field(description=IS_MINOR_FIELD_DESCRIPTION)
    guardian_name: Optional[str] = None
    guardian_document_type: Optional[str] = None
    guardian_document_number: Optional[str] = None
    guardian_document_issue_date: Optional[date] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("is_minor", mode="before")
    @classmethod
    def _coerce_bool(cls, v: object) -> bool:
        if v in (0, 1, "0", "1"):
            return bool(int(v))
        return bool(v)


class CustomerListResponse(BaseModel):
    items: list[CustomerPublic]
    total: int
    limit: int
    offset: int
