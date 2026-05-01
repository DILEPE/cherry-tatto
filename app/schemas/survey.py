"""Esquemas Pydantic: encuestas."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.models import Survey, SurveyAnswerWrite


class SurveyAnswerItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    question_id: int = Field(..., ge=1)
    rating: Optional[int] = Field(None, ge=1, le=5)
    yes_no: Optional[bool] = None
    text: Optional[str] = Field(None, max_length=5000)
    """Texto, opción única (radio/select), o JSON para checkbox si no usas `choices`."""
    choices: Optional[list[str]] = Field(None, max_length=64)
    """Respuestas múltiples (checkbox); se serializa a JSON en `survey_answers.answer_text`."""
    number: Optional[float] = None

    @field_validator("choices")
    @classmethod
    def choices_non_empty_strings(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return v
        out: list[str] = []
        for x in v:
            t = str(x).strip()
            if t:
                out.append(t)
        return out or None


class SurveyCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    appointment_id: int = Field(..., ge=1)
    rating: Optional[int] = Field(None, ge=1, le=5)
    comments: Optional[str] = Field(None, max_length=5000)
    would_recommend: bool = True
    answers: Optional[list[SurveyAnswerItem]] = None

    @field_validator("rating")
    @classmethod
    def rating_range(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return v
        if v < 1 or v > 5:
            raise ValueError("rating must be between 1 and 5")
        return v

    @model_validator(mode="after")
    def rating_required_without_answers(self) -> SurveyCreate:
        if not self.answers and self.rating is None:
            raise ValueError("rating es obligatoria si no envías respuestas dinámicas (answers)")
        return self


def survey_create_to_domain(req: SurveyCreate) -> Survey:
    answers: Optional[list[SurveyAnswerWrite]] = None
    if req.answers:
        answers = []
        for item in req.answers:
            text_val: Optional[str] = item.text
            if item.choices is not None:
                text_val = json.dumps(item.choices, ensure_ascii=False)
            answers.append(
                SurveyAnswerWrite(
                    question_id=item.question_id,
                    answer_rating=item.rating,
                    answer_bool=item.yes_no,
                    answer_text=text_val,
                    answer_number=item.number,
                )
            )
    rating_val = int(req.rating) if req.rating is not None else 3
    return Survey(
        appointment_id=req.appointment_id,
        rating=rating_val,
        comments=req.comments,
        would_recommend=req.would_recommend,
        answers=answers,
    )


class SurveyRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    appointment_id: int
    rating: int
    comments: Optional[str] = None
    would_recommend: Optional[bool] = None
    created_at: Optional[datetime] = None
