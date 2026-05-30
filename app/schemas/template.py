"""Esquemas Pydantic: plantillas de contrato (API)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import ContractTemplate

ContractKindLiteral = Literal["tattoo", "piercing"]
SigningFlowLiteral = Literal["phased", "single"]


class ContractTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: int
    name: str
    contract_kind: ContractKindLiteral = "tattoo"
    version: str
    content: str
    is_active: bool = True
    signing_flow: SigningFlowLiteral = "phased"


class ContractTemplateCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=200)
    contract_kind: ContractKindLiteral = "tattoo"
    version: str = Field(..., min_length=1, max_length=32)
    content: str = Field(..., min_length=1)
    is_active: bool = True
    signing_flow: SigningFlowLiteral = "phased"

    def to_domain(self) -> ContractTemplate:
        return ContractTemplate(
            id=None,
            name=self.name,
            version=self.version,
            content=self.content,
            contract_kind=self.contract_kind,
            is_active=self.is_active,
            signing_flow=self.signing_flow,
        )


class ContractTemplateUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=200)
    contract_kind: ContractKindLiteral = "tattoo"
    version: str = Field(..., min_length=1, max_length=32)
    content: str = Field(..., min_length=1)
    is_active: bool = True
    signing_flow: SigningFlowLiteral = "phased"

    def to_domain(self) -> ContractTemplate:
        return ContractTemplate(
            id=None,
            name=self.name,
            version=self.version,
            content=self.content,
            contract_kind=self.contract_kind,
            is_active=self.is_active,
            signing_flow=self.signing_flow,
        )
