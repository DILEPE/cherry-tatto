"""Esquemas HTTP para registro e inicio de sesión de usuarios del panel."""
from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

_USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,80}$")


class PanelUserRegister(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    username: str = Field(..., min_length=1, max_length=80)
    password: str = Field(..., min_length=8, max_length=72)

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


class PanelUserLogin(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    username: str = Field(..., min_length=1, max_length=80)
    password: str = Field(..., min_length=1, max_length=72)

    @field_validator("username")
    @classmethod
    def username_norm(cls, v: str) -> str:
        return v.strip().lower()


class PanelUserRegisteredResponse(BaseModel):
    status: str = "success"
    message: str
    id: int
