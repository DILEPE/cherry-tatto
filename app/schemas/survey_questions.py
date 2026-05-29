"""Esquemas Pydantic: preguntas configurables de encuesta."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.contract_kinds import SurveyQuestionScope
from app.domain.models import SurveyQuestion
from app.domain.survey_question_helpers import (
    QUESTION_TYPES_NEEDING_OPTIONS,
    parse_options_json,
)

QuestionTypeLiteral = Literal[
    "rating_1_5",
    "yes_no",
    "text",
    "radio",
    "checkbox",
    "select",
    "textarea",
    "text_short",
    "number",
]


class SurveyQuestionCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    label: str = Field(..., min_length=1, max_length=500)
    question_type: QuestionTypeLiteral
    options: Optional[list[str]] = Field(
        None,
        description="Obligatorio para radio, checkbox y select: al menos 2 opciones distintas",
    )
    sort_order: int = Field(0, ge=0, le=9999)
    contract_kind: SurveyQuestionScope = "tattoo"
    is_active: bool = True

    @staticmethod
    def _normalize_option_list(raw: Optional[list[str]]) -> Optional[list[str]]:
        if not raw:
            return None
        out: list[str] = []
        seen: set[str] = set()
        for x in raw:
            t = str(x).strip()
            if not t:
                raise ValueError("Las opciones no pueden ser cadenas vacías")
            if len(t) > 200:
                raise ValueError("Cada opción admite como máximo 200 caracteres")
            if t in seen:
                raise ValueError("Las opciones no pueden estar duplicadas")
            seen.add(t)
            out.append(t)
        return out or None

    @model_validator(mode="after")
    def validate_options_by_type(self) -> SurveyQuestionCreate:
        opts = self._normalize_option_list(self.options)
        self.options = opts
        if self.question_type in QUESTION_TYPES_NEEDING_OPTIONS:
            if not self.options or len(self.options) < 2:
                raise ValueError("Los tipos radio, checkbox y select requieren al menos 2 opciones")
        elif self.options:
            raise ValueError("Este tipo de pregunta no admite lista de opciones")
        if self.options and len(self.options) > 64:
            raise ValueError("Máximo 64 opciones")
        return self


class SurveyQuestionUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    label: Optional[str] = Field(None, min_length=1, max_length=500)
    question_type: Optional[QuestionTypeLiteral] = None
    options: Optional[list[str]] = None
    sort_order: Optional[int] = Field(None, ge=0, le=9999)
    contract_kind: Optional[SurveyQuestionScope] = None
    is_active: Optional[bool] = None

    @model_validator(mode="after")
    def normalize_options_when_present(self) -> SurveyQuestionUpdate:
        if self.options is not None:
            self.options = SurveyQuestionCreate._normalize_option_list(self.options)
        return self


class SurveyQuestionRead(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    label: str
    question_type: str
    options: Optional[list[str]] = None
    sort_order: int
    contract_kind: SurveyQuestionScope = "tattoo"
    is_active: bool
    created_at: Optional[datetime] = None

    @model_validator(mode="before")
    @classmethod
    def options_from_json_column(cls, data: Any) -> Any:
        if isinstance(data, dict):
            d = dict(data)
            if d.get("options") is None:
                d["options"] = parse_options_json(d.get("options_json"))
            return d
        return data


class SurveyQuestionDeletionImpact(BaseModel):
    question_id: int
    label: str
    registered_answers: int


class SurveyQuestionStatRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    question_id: int
    label: str
    question_type: str
    sort_order: int
    contract_kind: SurveyQuestionScope = "tattoo"
    is_active: bool
    response_count: int
    avg_rating: Optional[float] = None
    yes_count: Optional[int] = None
    no_count: Optional[int] = None
    text_response_count: Optional[int] = None
    avg_number: Optional[float] = None
    rating_breakdown: Optional[dict[str, int]] = None
    number_breakdown: Optional[dict[str, int]] = None
    choice_breakdown: Optional[dict[str, int]] = None


class SurveyQuestionTextResponseRow(BaseModel):
    """Respuesta de texto libre vinculada al cliente de la cita."""

    customer_id: Optional[int] = None
    response_text: str


def question_create_to_domain(data: SurveyQuestionCreate) -> SurveyQuestion:
    return SurveyQuestion(
        id=None,
        label=data.label,
        question_type=data.question_type,
        options=data.options,
        sort_order=data.sort_order,
        contract_kind=data.contract_kind,
        is_active=data.is_active,
    )
