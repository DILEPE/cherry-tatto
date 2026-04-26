"""Esquemas Pydantic: citas."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.models import AppointmentCreate
from app.schemas.customer import CustomerCreate

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class AppointmentCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=200)
    phone: str = Field(..., min_length=5, max_length=40)
    service: str = Field(..., min_length=1, max_length=120)
    date: str = Field(..., description="YYYY-MM-DD")
    detail: Optional[str] = Field(None, max_length=5000)
    deposit: float = Field(ge=0, default=0)
    total_amount: float = Field(ge=0, default=0)
    pending_balance: float = Field(ge=0, default=0)
    customer_id: Optional[int] = Field(default=None, ge=1)
    customer: Optional[CustomerCreate] = None

    @field_validator("date")
    @classmethod
    def date_ok(cls, v: str) -> str:
        if not _DATE.match(v):
            raise ValueError("date must be YYYY-MM-DD")
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError as e:
            raise ValueError("invalid calendar date") from e
        return v


def appointment_request_to_domain(req: AppointmentCreateRequest) -> AppointmentCreate:
    """Convierte el cuerpo validado de la API al dataclass de persistencia."""
    return AppointmentCreate(
        name=req.name,
        phone=req.phone,
        service=req.service,
        date=req.date,
        detail=req.detail,
        deposit=req.deposit,
        total_amount=req.total_amount,
        pending_balance=req.pending_balance,
        customer_id=req.customer_id,
        customer=req.customer.model_dump(mode="json") if req.customer is not None else None,
    )


class AppointmentListItem(BaseModel):
    """Fila típica de `SELECT * FROM appointments` (campos opcionales por versiones de esquema)."""
    model_config = ConfigDict(extra="ignore")

    id: int
    customer_name: Optional[str] = None
    phone: Optional[str] = None
    service_type: Optional[str] = None
    detail: Optional[str] = None
    appointment_date: Optional[date | str] = None
    deposit: Optional[float] = None
    total_amount: Optional[float] = None
    pending_balance: Optional[float] = None
    customer_credit: Optional[float] = None
    status: Optional[str] = None
    customer_id: Optional[int] = None
    created_at: Optional[datetime | str] = None


class AppointmentStatusUpdateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    status: str = Field(..., min_length=1, max_length=30)

    @field_validator("status")
    @classmethod
    def status_ok(cls, v: str) -> str:
        valid = {"Agendada", "Reprogramada", "Cancelada", "Finalizada"}
        if v not in valid:
            raise ValueError("status inválido")
        return v


class AppointmentRescheduleRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    date: str = Field(..., description="YYYY-MM-DD")
    detail: Optional[str] = Field(None, max_length=5000)

    @field_validator("date")
    @classmethod
    def date_ok(cls, v: str) -> str:
        if not _DATE.match(v):
            raise ValueError("date must be YYYY-MM-DD")
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError as e:
            raise ValueError("invalid calendar date") from e
        return v


class AppointmentFinancialUpdateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    total_amount: float = Field(ge=0)
    deposit: float = Field(ge=0)
    pending_balance: float = Field(ge=0)

    @field_validator("pending_balance")
    @classmethod
    def pending_must_match(cls, v: float, info) -> float:
        total = float(info.data.get("total_amount", 0))
        deposit = float(info.data.get("deposit", 0))
        expected = round(total - deposit, 2)
        if round(v, 2) != expected:
            raise ValueError("pending_balance debe ser total_amount - deposit")
        if expected < 0:
            raise ValueError("pending_balance no puede ser negativo")
        return v
