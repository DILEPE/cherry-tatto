"""Esquemas Pydantic: firma de contratos."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from app.domain.models import ContractSign


class ContractSignRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    appointment_id: int = Field(..., ge=1)
    is_minor: bool = False
    health_data: dict[str, JsonValue]
    signature: str = Field(..., min_length=1, max_length=2000)
    tutor_signature: Optional[str] = Field(None, max_length=2000)
    template_id: Optional[int] = Field(None, ge=1)

    @field_validator("health_data")
    @classmethod
    def health_not_empty(cls, v: dict[str, JsonValue]) -> dict[str, JsonValue]:
        if not v:
            raise ValueError("health_data must not be empty")
        return v


def contract_sign_to_domain(req: ContractSignRequest) -> ContractSign:
    return ContractSign(
        appointment_id=req.appointment_id,
        is_minor=req.is_minor,
        health_data=req.health_data,
        signature=req.signature,
        tutor_signature=req.tutor_signature,
        template_id=req.template_id,
    )
