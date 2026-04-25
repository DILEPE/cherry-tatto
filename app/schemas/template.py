"""Esquemas Pydantic: plantillas de contrato (API)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import ContractTemplate


class ContractTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: int
    name: str
    version: str
    content: str
    is_active: bool = True


class ContractTemplateCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=200)
    version: str = Field(..., min_length=1, max_length=32)
    content: str = Field(..., min_length=1)
    is_active: bool = True

    def to_domain(self) -> ContractTemplate:
        return ContractTemplate(
            id=None,
            name=self.name,
            version=self.version,
            content=self.content,
            is_active=self.is_active,
        )


class ContractTemplateUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=200)
    version: str = Field(..., min_length=1, max_length=32)
    content: str = Field(..., min_length=1)
    is_active: bool = True

    def to_domain(self) -> ContractTemplate:
        return ContractTemplate(
            id=None,
            name=self.name,
            version=self.version,
            content=self.content,
            is_active=self.is_active,
        )
