from __future__ import annotations

from litestar import Controller, get, post, status_codes
from litestar.datastructures import State
from litestar.exceptions import HTTPException

from app.schemas.common import ApiSuccessResponse
from app.schemas.survey import SurveyAppointmentLookup, SurveyCreate, SurveyRow, survey_create_to_domain


class SurveyController(Controller):
    """Controlador para manejar las encuestas de satisfacción."""
    path = "/api/surveys"

    @post(status_code=status_codes.HTTP_201_CREATED)
    async def create_survey(self, data: SurveyCreate, state: State) -> ApiSuccessResponse:
        """Punto de entrada para recibir encuestas."""
        try:
            new_id = await state.service.register_survey(survey_create_to_domain(data))
            return ApiSuccessResponse(
                status="success",
                message="Survey registered successfully.",
                id=new_id,
            )
        except Exception as e:
            raise HTTPException(detail=f"Error: {str(e)}", status_code=500) from e

    @get("/by-appointment/{appointment_id:int}")
    async def survey_for_appointment(
        self,
        appointment_id: int,
        state: State,
    ) -> SurveyAppointmentLookup:
        """Indica si la cita ya tiene encuesta registrada (sin listar todas las encuestas)."""
        try:
            survey = await state.service.get_survey_by_appointment(appointment_id)
            return SurveyAppointmentLookup(found=survey is not None, survey=survey)
        except Exception as e:
            raise HTTPException(detail=f"Error al consultar encuesta: {str(e)}", status_code=500) from e

    @get("/")
    async def list_surveys(self, state: State) -> list[SurveyRow]:
        """Lista todas las encuestas registradas."""
        try:
            return await state.service.list_surveys()
        except Exception as e:
            raise HTTPException(detail=f"Error al listar encuestas: {str(e)}", status_code=500) from e
