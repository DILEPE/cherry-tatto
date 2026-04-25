"""Esquemas Pydantic: encuestas."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.models import Survey


class SurveyCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    appointment_id: int = Field(..., ge=1)
    rating: int
    comments: Optional[str] = Field(None, max_length=5000)
    would_recommend: bool = True

    @field_validator("rating")
    @classmethod
    def rating_range(cls, v: int) -> int:
        if v < 1 or v > 5:
            raise ValueError("rating must be between 1 and 5")
        return v


def survey_create_to_domain(req: SurveyCreate) -> Survey:
    return Survey(
        appointment_id=req.appointment_id,
        rating=req.rating,
        comments=req.comments,
        would_recommend=req.would_recommend,
    )


class SurveyRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    appointment_id: int
    rating: int
    comments: Optional[str] = None
    would_recommend: Optional[bool] = None
    created_at: Optional[datetime] = None
