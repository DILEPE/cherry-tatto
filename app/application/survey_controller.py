from typing import Any, Dict, List

from litestar import Controller, get, post, status_codes
from litestar.datastructures import State
from litestar.exceptions import HTTPException

from app.domain.models import APIResponse, Survey


class SurveyController(Controller):
    """Controlador para manejar las encuestas de satisfacción."""
    path = "/api/surveys"

    @post(status_code=status_codes.HTTP_201_CREATED)
    async def create_survey(self, data: Survey, state: State) -> APIResponse:
        """Punto de entrada para recibir encuestas."""
        try:
            new_id = await state.service.register_survey(data)
            return APIResponse(
                status="success",
                message="Survey registered successfully.",
                id=new_id,
            )
        except Exception as e:
            raise HTTPException(detail=f"Error: {str(e)}", status_code=500)

    @get("/")
    async def list_surveys(self, state: State) -> List[Dict[str, Any]]:
        """Lista todas las encuestas registradas."""
        try:
            return await state.service.list_surveys()
        except Exception as e:
            raise HTTPException(detail=f"Error al listar encuestas: {str(e)}", status_code=500)
