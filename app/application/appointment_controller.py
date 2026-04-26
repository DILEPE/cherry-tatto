from __future__ import annotations

from litestar import Controller, patch, get, post, status_codes
from litestar.datastructures import State
from litestar.exceptions import HTTPException

from app.schemas.appointment import (
    AppointmentCreateRequest,
    AppointmentFinancialUpdateRequest,
    AppointmentListItem,
    AppointmentPaymentCreateRequest,
    AppointmentPaymentItem,
    AppointmentRescheduleRequest,
    AppointmentStatusUpdateRequest,
    appointment_request_to_domain,
)
from app.schemas.common import AppointmentCreatedResponse, MessageResponse


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

    @patch("/{appointment_id:int}/status")
    async def update_status(
        self,
        appointment_id: int,
        data: AppointmentStatusUpdateRequest,
        state: State,
    ) -> MessageResponse:
        try:
            await state.service.update_appointment_status(appointment_id, data.status)
            return MessageResponse(status="success", message=f"Estado actualizado a {data.status}")
        except ValueError as e:
            raise HTTPException(detail=str(e), status_code=404) from e
        except Exception as e:
            raise HTTPException(detail=f"Error al actualizar estado: {str(e)}", status_code=400) from e

    @patch("/{appointment_id:int}/reschedule")
    async def reprogram(
        self,
        appointment_id: int,
        data: AppointmentRescheduleRequest,
        state: State,
    ) -> MessageResponse:
        try:
            await state.service.reprogram_appointment(appointment_id, data.date, data.detail)
            return MessageResponse(status="success", message="Cita reprogramada correctamente")
        except ValueError as e:
            raise HTTPException(detail=str(e), status_code=404) from e
        except Exception as e:
            raise HTTPException(detail=f"Error al reprogramar cita: {str(e)}", status_code=400) from e

    @patch("/{appointment_id:int}/financials")
    async def update_financials(
        self,
        appointment_id: int,
        data: AppointmentFinancialUpdateRequest,
        state: State,
    ) -> MessageResponse:
        try:
            await state.service.update_appointment_financials(
                appointment_id,
                data.total_amount,
                data.deposit,
                data.pending_balance,
            )
            return MessageResponse(status="success", message="Montos actualizados correctamente")
        except ValueError as e:
            raise HTTPException(detail=str(e), status_code=400) from e
        except Exception as e:
            raise HTTPException(detail=f"Error al actualizar montos: {str(e)}", status_code=400) from e

    @get("/{appointment_id:int}/payments")
    async def list_payments(self, appointment_id: int, state: State) -> list[AppointmentPaymentItem]:
        try:
            rows = await state.service.list_appointment_payments(appointment_id)
            return [AppointmentPaymentItem.model_validate(r) for r in rows]
        except ValueError as e:
            raise HTTPException(detail=str(e), status_code=404) from e
        except Exception as e:
            raise HTTPException(detail=f"Error al obtener historial de abonos: {str(e)}", status_code=400) from e

    @post("/{appointment_id:int}/payments")
    async def add_payment(
        self,
        appointment_id: int,
        data: AppointmentPaymentCreateRequest,
        state: State,
    ) -> MessageResponse:
        try:
            await state.service.add_appointment_payment(appointment_id, data.amount, data.note)
            return MessageResponse(status="success", message="Abono registrado correctamente")
        except ValueError as e:
            raise HTTPException(detail=str(e), status_code=400) from e
        except Exception as e:
            raise HTTPException(detail=f"Error al registrar abono: {str(e)}", status_code=400) from e
