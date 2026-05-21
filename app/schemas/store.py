"""Esquemas Pydantic: tiendas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StoreCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=200)
    address: Optional[str] = Field(None, max_length=500)
    phone: Optional[str] = Field(None, max_length=40)
    email: Optional[str] = Field(None, max_length=120)
    is_active: bool = True


class StoreUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=200)
    address: Optional[str] = Field(None, max_length=500)
    phone: Optional[str] = Field(None, max_length=40)
    email: Optional[str] = Field(None, max_length=120)
    is_active: bool = True


class StorePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: int
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("is_active", mode="before")
    @classmethod
    def _coerce_bool(cls, v: object) -> bool:
        if v in (0, 1, "0", "1"):
            return bool(int(v))
        return bool(v)


class StoreCreatedResponse(BaseModel):
    id: int
    status: str = "success"
    message: str = "Tienda creada"
