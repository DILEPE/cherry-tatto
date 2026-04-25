from __future__ import annotations

from litestar import Controller, get, post, status_codes
from litestar.datastructures import State
from litestar.exceptions import HTTPException

from app.schemas.appointment import (
    AppointmentCreateRequest,
    AppointmentListItem,
    appointment_request_to_domain,
)
from app.schemas.common import AppointmentCreatedResponse


class AppointmentController(Controller):
    path = "/api/appointments"

    @get()
    async def list_all(self, state: State) -> list[AppointmentListItem]:
        """Lista todas las citas registradas."""
        try:
            return await state.service.list_appointments()
        except Exception as e:
            raise HTTPException(detail=f"Error al obtener citas: {str(e)}", status_code=500)

    @post(status_code=status_codes.HTTP_201_CREATED)
    async def create(self, data: AppointmentCreateRequest, state: State) -> AppointmentCreatedResponse:
        """
        Crea una nueva cita.
        Si el vendedor la crea desde la tablet, se dispara la confirmación en n8n.
        """
        try:
            service = state.service
            new_id = await service.register_appointment(appointment_request_to_domain(data))
            return AppointmentCreatedResponse(
                id=new_id,
                status="success",
                message="Cita creada y notificación enviada a n8n",
            )
        except ValueError as e:
            raise HTTPException(detail=str(e), status_code=400) from e
        except Exception as e:
            raise HTTPException(detail=f"Error al crear cita: {str(e)}", status_code=400) from e
