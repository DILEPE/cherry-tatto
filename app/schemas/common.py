"""Tipos y modelos de respuesta comunes de la API (Pydantic v2)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ApiSuccessResponse(BaseModel):
    """Operación correcta, mensaje e id opcional (p. ej. registro creado)."""
    model_config = ConfigDict(str_strip_whitespace=True)

    status: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    id: Optional[int] = None


class AppointmentCreatedResponse(BaseModel):
    id: int
    status: str
    message: str


class MessageResponse(BaseModel):
    status: str
    message: str


class CustomerCreatedResponse(BaseModel):
    id: int
    status: str
    message: str
