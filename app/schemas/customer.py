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

    @model_validator(mode="after")
    def guardian_if_minor(self) -> "CustomerCreate":
        if self.is_minor:
            if not self.guardian_name or not self.guardian_document_type or not self.guardian_document_number:
                raise ValueError(
                    "When is_minor is true, guardian_name, guardian_document_type and "
                    "guardian_document_number are required."
                )
        return self


class CustomerUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    birth_date: date
    document_type: DocumentType
    document_number: str = Field(..., min_length=5, max_length=32)
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

    @model_validator(mode="after")
    def guardian_if_minor(self) -> "CustomerUpdate":
        if self.is_minor:
            if not self.guardian_name or not self.guardian_document_type or not self.guardian_document_number:
                raise ValueError(
                    "When is_minor is true, guardian_name, guardian_document_type and "
                    "guardian_document_number are required."
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
