"""Pydantic schemas for customer API validation."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, JsonValue, field_validator, model_validator

DocumentType = Literal["CC", "TI", "CE", "PAS"]


class CustomerCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    birth_date: date
    document_type: DocumentType
    document_number: str = Field(..., min_length=5, max_length=32)
    document_issue_date: Optional[date] = None
    email: EmailStr
    phone_number: str = Field(..., min_length=7, max_length=32)
    address: Optional[str] = Field(None, max_length=500)
    nationality: Optional[str] = Field(None, max_length=100)
    profession: Optional[str] = Field(None, max_length=150)
    secondary_email: Optional[EmailStr] = None
    social_media: Optional[dict[str, JsonValue]] = None
    emergency_contact_name: Optional[str] = Field(None, max_length=150)
    emergency_contact_phone: Optional[str] = Field(None, max_length=32)
    is_minor: bool = False
    guardian_name: Optional[str] = Field(None, max_length=200)
    guardian_document_type: Optional[DocumentType] = None
    guardian_document_number: Optional[str] = Field(None, max_length=32)
    guardian_document_issue_date: Optional[date] = None

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
    model_config = ConfigDict(str_strip_whitespace=True)

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    birth_date: date
    document_type: DocumentType
    document_number: str = Field(..., min_length=5, max_length=32)
    document_issue_date: Optional[date] = None
    email: EmailStr
    phone_number: str = Field(..., min_length=7, max_length=32)
    address: Optional[str] = Field(None, max_length=500)
    nationality: Optional[str] = Field(None, max_length=100)
    profession: Optional[str] = Field(None, max_length=150)
    secondary_email: Optional[EmailStr] = None
    social_media: Optional[dict[str, JsonValue]] = None
    emergency_contact_name: Optional[str] = Field(None, max_length=150)
    emergency_contact_phone: Optional[str] = Field(None, max_length=32)
    is_minor: bool = False
    guardian_name: Optional[str] = Field(None, max_length=200)
    guardian_document_type: Optional[DocumentType] = None
    guardian_document_number: Optional[str] = Field(None, max_length=32)
    guardian_document_issue_date: Optional[date] = None

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
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    last_name: str
    birth_date: date
    document_type: str
    document_number: str
    document_issue_date: Optional[date] = None
    email: str
    phone_number: str
    address: Optional[str] = None
    nationality: Optional[str] = None
    profession: Optional[str] = None
    secondary_email: Optional[str] = None
    social_media: Optional[dict[str, JsonValue]] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    is_minor: bool
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
