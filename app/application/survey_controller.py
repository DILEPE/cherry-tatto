from litestar import Controller, post, get, status_codes
from litestar.datastructures import State
from litestar.exceptions import HTTPException
from app.domain.models import Survey, APIResponse
from typing import List, Dict, Any, Optional
from app.domain.models import AppointmentCreate, ContractSign, ContractTemplate, Survey


class BusinessLogicService:
    def __init__(self, repository, notifier):
        self.repository = repository
        self.notifier = notifier

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
                id=new_id
            )
        except Exception as e:
            raise HTTPException(detail=f"Error: {str(e)}", status_code=500)

    @get("/")
    async def list_surveys(self, state: State) -> List[Dict[str, Any]]:
        """Lista todas las encuestas registradas."""
        return state.service.repository.get_surveys()