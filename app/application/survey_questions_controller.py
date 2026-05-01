from __future__ import annotations

from litestar import Controller, delete, get, post, put, status_codes
from litestar.datastructures import State
from litestar.exceptions import HTTPException

from app.schemas.common import ApiSuccessResponse
from app.schemas.survey_questions import (
    SurveyQuestionCreate,
    SurveyQuestionDeletionImpact,
    SurveyQuestionRead,
    SurveyQuestionStatRow,
    SurveyQuestionUpdate,
)


class SurveyQuestionController(Controller):
    """CRUD de preguntas configurables para encuestas de satisfacción."""
    path = "/api/survey-questions"

    @get("/stats/summary")
    async def stats_summary(self, state: State) -> list[SurveyQuestionStatRow]:
        try:
            return await state.service.survey_question_stats_summary()
        except Exception as e:
            raise HTTPException(detail=f"Error al calcular estadísticas: {e}", status_code=500) from e

    @get("/")
    async def list_questions(
        self,
        state: State,
        include_inactive: bool = False,
        contract_kind: str | None = None,
    ) -> list[SurveyQuestionRead]:
        try:
            return await state.service.list_survey_questions(
                include_inactive=include_inactive,
                contract_kind=contract_kind,
            )
        except ValueError as e:
            raise HTTPException(detail=str(e), status_code=400) from e
        except Exception as e:
            raise HTTPException(detail=f"Error al listar preguntas: {e}", status_code=500) from e

    @get("/{question_id:int}/deletion-impact", status_code=status_codes.HTTP_200_OK)
    async def deletion_impact(self, state: State, question_id: int) -> SurveyQuestionDeletionImpact:
        try:
            return await state.service.survey_question_deletion_impact(question_id)
        except ValueError as e:
            raise HTTPException(detail=str(e), status_code=404) from e
        except Exception as e:
            raise HTTPException(detail=str(e), status_code=500) from e

    @post("/", status_code=status_codes.HTTP_201_CREATED)
    async def create_question(self, data: SurveyQuestionCreate, state: State) -> ApiSuccessResponse:
        try:
            new_id = await state.service.create_survey_question(data)
            return ApiSuccessResponse(
                status="success",
                message="Pregunta creada",
                id=new_id,
            )
        except Exception as e:
            raise HTTPException(detail=f"Error al crear pregunta: {e}", status_code=500) from e

    @put("/{question_id:int}")
    async def update_question(
        self,
        question_id: int,
        data: SurveyQuestionUpdate,
        state: State,
    ) -> ApiSuccessResponse:
        try:
            await state.service.update_survey_question(question_id, data)
            return ApiSuccessResponse(status="success", message=f"Pregunta {question_id} actualizada")
        except ValueError as e:
            raise HTTPException(detail=str(e), status_code=404) from e
        except Exception as e:
            raise HTTPException(detail=f"Error al actualizar: {e}", status_code=500) from e

    @delete("/{question_id:int}", status_code=status_codes.HTTP_200_OK)
    async def delete_question(self, question_id: int, state: State) -> ApiSuccessResponse:
        try:
            await state.service.delete_survey_question(question_id)
            return ApiSuccessResponse(status="success", message=f"Pregunta {question_id} eliminada")
        except ValueError as e:
            raise HTTPException(detail=str(e), status_code=404) from e
        except Exception as e:
            raise HTTPException(detail=f"Error al eliminar: {e}", status_code=500) from e
