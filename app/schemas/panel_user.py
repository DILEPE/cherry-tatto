"""Esquemas HTTP para usuarios del panel (registro, login, gestión)."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Literal, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.domain.panel_user_profile import PANEL_ROLE_CHOICES

_USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,80}$")

PanelRolePayload = Literal["administrador", "vendedor", "perforador", "tatuador"]


class PanelUserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    first_name: str
    last_name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    store_id: int
    store_name: Optional[str] = None
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PanelUserAssignable(BaseModel):
    """Usuario del panel que puede recibir citas (tatuador o perforador)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    first_name: str
    last_name: str
    role: str


def _norm_optional_str(v: Optional[str], *, max_len: int) -> Optional[str]:
    if v is None:
        return None
    s = v.strip()
    if not s:
        return None
    return s[:max_len]


class PanelUserRegister(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    username: str = Field(..., min_length=1, max_length=80)
    password: str = Field(..., min_length=8, max_length=72)
    first_name: str = Field(default="", max_length=100)
    last_name: str = Field(default="", max_length=100)
    address: Optional[str] = Field(default=None, max_length=500)
    phone: Optional[str] = Field(default=None, max_length=32)
    store_id: int = Field(..., ge=1)
    role: PanelRolePayload = "vendedor"

    @field_validator("username")
    @classmethod
    def username_rules(cls, v: str) -> str:
        s = v.strip().lower()
        if not _USERNAME_RE.fullmatch(s):
            raise ValueError(
                "El usuario debe tener entre 3 y 80 caracteres (solo letras minúsculas, números, "
                "punto, guion y guion bajo)."
            )
        return s

    @field_validator("first_name", "last_name")
    @classmethod
    def strip_names(cls, v: str) -> str:
        return (v or "").strip()[:100]

    @field_validator("address", mode="before")
    @classmethod
    def addr_norm(cls, v):
        return _norm_optional_str(v if isinstance(v, str) else None, max_len=500)

    @field_validator("phone", mode="before")
    @classmethod
    def phone_norm(cls, v):
        return _norm_optional_str(v if isinstance(v, str) else None, max_len=32)

    @field_validator("role")
    @classmethod
    def role_ok(cls, v: str) -> str:
        if v not in PANEL_ROLE_CHOICES:
            raise ValueError("Rol no válido.")
        return v


class PanelUserCreate(PanelUserRegister):
    """Alta completa desde el gestor (mismo cuerpo que registro + flag opcional)."""

    is_active: bool = True


class PanelUserLogin(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    username: str = Field(..., min_length=1, max_length=80)
    password: str = Field(..., min_length=1, max_length=72)


class PanelUserLoginResponse(BaseModel):
    """Respuesta de POST /panel-users/login (Streamlit lee `user`)."""

    status: str = "success"
    message: str
    user: PanelUserSessionPublic


class PanelUserSessionPublic(BaseModel):
    id: int
    username: str
    role: str
    session_expires_at: float


class PanelUserRegisteredResponse(BaseModel):
    message: str
    id: int


class PanelUserModulesBody(BaseModel):
    """PUT /panel-users/{id}/modules — JSON con ``modules`` o ``module_keys``."""

    model_config = ConfigDict(populate_by_name=True)

    modules: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("modules", "module_keys"),
    )

    @property
    def module_keys(self) -> list[str]:
        """Alias de lectura (servicio y clientes que usan ``module_keys``)."""
        return self.modules


class PanelUserUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    address: Optional[str] = Field(None, max_length=500)
    phone: Optional[str] = Field(None, max_length=32)
    store_id: Optional[int] = Field(None, ge=1)
    role: Optional[PanelRolePayload] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=8, max_length=72)

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def strip_names_opt(cls, v):
        if v is None:
            return None
        return str(v).strip()[:100]

    @field_validator("address", mode="before")
    @classmethod
    def addr_norm(cls, v):
        if v is None:
            return None
        if not isinstance(v, str):
            return None
        return _norm_optional_str(v, max_len=500)

    @field_validator("phone", mode="before")
    @classmethod
    def phone_norm(cls, v):
        if v is None:
            return None
        if not isinstance(v, str):
            return None
        return _norm_optional_str(v, max_len=32)

    @field_validator("role")
    @classmethod
    def role_ok(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if v not in PANEL_ROLE_CHOICES:
            raise ValueError("Rol no válido.")
        return v
