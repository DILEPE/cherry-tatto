from __future__ import annotations

from typing import Optional

from litestar import Controller, patch, get, post, status_codes
from litestar.datastructures import State
from litestar.exceptions import HTTPException
from litestar.params import Parameter
from litestar.response import Response

from app.schemas.appointment import (
    AppointmentCreateRequest,
    AppointmentFinancialUpdateRequest,
    AppointmentListItem,
    AppointmentPaymentCreateRequest,
    AppointmentPaymentItem,
    AppointmentPaymentReceiptListItem,
    AppointmentRescheduleRequest,
    AppointmentStatusUpdateRequest,
    appointment_request_to_domain,
)
from app.schemas.common import (
    AppointmentCreatedResponse,
    AppointmentPaymentCreatedResponse,
    MessageResponse,
)


class AppointmentController(Controller):
    path = "/api/appointments"

    @get()
    async def list_all(
        self,
        state: State,
        assigned_panel_user_id: Optional[int] = Parameter(
            default=None, ge=1, query="assigned_panel_user_id"
        ),
    ) -> list[AppointmentListItem]:
        """Lista citas; opcionalmente solo las asignadas a un profesional del panel."""
        try:
            return await state.service.list_appointments(
                assigned_panel_user_id=assigned_panel_user_id,
            )
        except Exception as e:
            raise HTTPException(detail=f"Error al obtener citas: {str(e)}", status_code=500)

    @get("/{appointment_id:int}")
    async def get_one(self, appointment_id: int, state: State) -> AppointmentListItem:
        """Detalle de una cita (mismo formato que el listado)."""
        try:
            return await state.service.get_appointment_detail(appointment_id)
        except ValueError as e:
            raise HTTPException(detail=str(e), status_code=404) from e
        except Exception as e:
            raise HTTPException(detail=f"Error al obtener cita: {str(e)}", status_code=500) from e

    @post(status_code=status_codes.HTTP_201_CREATED)
    async def create(self, data: AppointmentCreateRequest, state: State) -> AppointmentCreatedResponse:
        """
        Crea una nueva cita.
        Si el vendedor la crea desde la tablet, se dispara la confirmación en n8n.

        **Cliente embebido (`customer`):** si el documento aún no existe, puede enviarse el alta sin fecha de nacimiento
        real usando el sentinela documentado en el esquema `CustomerCreate` (`birth_date` de nacimiento pendiente,
        `is_minor=false`, sin expedición de documento). Los datos se completan después con `PUT /api/customers/{id}`.
        """
        try:
            service = state.service
            new_id, customer_id = await service.register_appointment(appointment_request_to_domain(data))
            return AppointmentCreatedResponse(
                id=new_id,
                status="success",
                message="Cita creada y notificación enviada a n8n",
                customer_id=customer_id,
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
            await state.service.update_appointment_status(
                appointment_id,
                data.status,
                data.on_cancel_abono if data.status == "Cancelada" else None,
            )
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
    ) -> AppointmentPaymentCreatedResponse:
        try:
            pid = await state.service.add_appointment_payment(appointment_id, data.amount, data.note)
            return AppointmentPaymentCreatedResponse(
                status="success",
                message="Abono registrado correctamente",
                payment_id=pid,
            )
        except ValueError as e:
            raise HTTPException(detail=str(e), status_code=400) from e
        except Exception as e:
            raise HTTPException(detail=f"Error al registrar abono: {str(e)}", status_code=400) from e

    @get("/{appointment_id:int}/receipts")
    async def list_receipts(
        self,
        appointment_id: int,
        state: State,
    ) -> list[AppointmentPaymentReceiptListItem]:
        try:
            rows = await state.service.list_appointment_payment_receipts(appointment_id)
            return [AppointmentPaymentReceiptListItem.model_validate(r) for r in rows]
        except ValueError as e:
            raise HTTPException(detail=str(e), status_code=404) from e
        except Exception as e:
            raise HTTPException(detail=f"Error al listar recibos: {str(e)}", status_code=400) from e

    @get("/{appointment_id:int}/receipts/{receipt_id:int}/pdf")
    async def download_receipt_pdf(
        self,
        appointment_id: int,
        receipt_id: int,
        state: State,
    ) -> Response:
        try:
            pdf_bytes, filename = await state.service.get_appointment_receipt_pdf(appointment_id, receipt_id)
            safe_name = filename.replace('"', "").replace("\r", "").replace("\n", "") or "recibo.pdf"
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
            )
        except ValueError as e:
            raise HTTPException(detail=str(e), status_code=404) from e
        except Exception as e:
            raise HTTPException(detail=f"Error al descargar recibo: {str(e)}", status_code=400) from e
