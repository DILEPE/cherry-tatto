from typing import Any, Dict, List
from litestar import Controller, get, post, status_codes
from litestar.exceptions import HTTPException
from litestar.datastructures import State
from app.domain.models import AppointmentCreate
from app.domain.models import AppointmentResponse

class AppointmentController(Controller):
    path = "/api/appointments"

    @get()
    async def list_all(self, state: State) -> List[Dict[str, Any]]:
        """Lista todas las citas registradas."""
        try:
            appointments = await state.service.list_appointments()
            return appointments
        except Exception as e:
            raise HTTPException(detail=f"Error al obtener citas: {str(e)}", status_code=500)

    @post(status_code=status_codes.HTTP_201_CREATED)
    async def create(self, data: AppointmentCreate, state: State) -> AppointmentResponse:
        """
        Crea una nueva cita. 
        Si el vendedor la crea desde la tablet, se dispara la confirmación en n8n.
        """
        try:
            service = state.service
            new_id = await service.register_appointment(data)
            return AppointmentResponse(
                id=new_id,
                status="success",
                message="Cita creada y notificación enviada a n8n"
            )
              
        except ValueError as e:
            raise HTTPException(detail=str(e), status_code=400)
        except Exception as e:
            raise HTTPException(detail=f"Error al crear cita: {str(e)}", status_code=400)