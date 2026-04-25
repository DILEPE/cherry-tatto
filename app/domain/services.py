import asyncio
import logging
from typing import Optional

import mysql.connector

from app.domain.models import (
    AppointmentCreate,
    ContractSign,
    Survey,
)
from app.schemas.appointment import AppointmentListItem
from app.schemas.customer import (
    CustomerCreate,
    CustomerListResponse,
    CustomerPublic,
    CustomerUpdate,
)
from app.schemas.report import FinancialReportRow
from app.schemas.survey import SurveyRow
from app.schemas.template import ContractTemplateCreate, ContractTemplateRead, ContractTemplateUpdate

logger = logging.getLogger(__name__)


class BusinessLogicService:
    """
    Capa de dominio / aplicación: orquesta citas, clientes, plantillas y notificaciones.
    """

    def __init__(self, appointment_repository, customer_repository, notifier):
        self.repository = appointment_repository
        self.customers = customer_repository
        self.notifier = notifier

    # --- Citas + cliente ---

    async def register_appointment(self, data: AppointmentCreate) -> int:
        """
        Crea cita. Si viene `customer` (dict), valida con Pydantic y hace upsert por documento.
        Si viene `customer_id`, verifica existencia. Usa transacción para cliente + cita.
        """
        def _sync_register() -> tuple[int, Optional[int]]:
            with self.repository.db.transaction() as conn:
                resolved_id: Optional[int] = data.customer_id
                if data.customer is not None:
                    c = CustomerCreate.model_validate(data.customer)
                    resolved_id = self.customers.upsert_by_document(c, conn)
                elif resolved_id is not None:
                    row = self.customers.get_by_id(resolved_id, conn)
                    if row is None:
                        raise ValueError(f"Cliente id={resolved_id} no encontrado.")
                new_id = self.repository.create(data, resolved_id, conn)
                logger.info(
                    "Appointment created id=%s customer_id=%s",
                    new_id,
                    resolved_id,
                )
                return new_id, resolved_id

        new_id, customer_id = await asyncio.to_thread(_sync_register)

        payload: dict[str, object] = {
            "id": new_id,
            "name": data.name,
            "phone": data.phone,
            "service": data.service,
            "date": data.date,
            "customer_id": customer_id,
        }
        asyncio.create_task(self._async_notify("appointment_created", payload))
        return new_id

    async def process_contract_signature(self, data: ContractSign) -> None:
        appointment = self.repository.get_by_id(data.appointment_id)
        if not appointment:
            raise ValueError(f"Cita con ID {data.appointment_id} no encontrada.")

        self.repository.create_contract(data)
        self.repository.update_status(data.appointment_id, "Completado")

        notification_payload: dict[str, object] = {
            "appointment_id": data.appointment_id,
            "customer_name": appointment.name,
            "phone": appointment.phone,
            "service": appointment.service,
            "health_summary": data.health_data,
        }
        asyncio.create_task(self._async_notify("contract_signed", notification_payload))

    async def register_survey(self, data: Survey) -> int:
        new_id = self.repository.create_survey(data)
        if data.rating <= 2:
            pl: dict[str, object] = {
                "appointment_id": data.appointment_id,
                "rating": data.rating,
                "comments": data.comments,
            }
            asyncio.create_task(self._async_notify("survey_low_rating", pl))
        return new_id

    async def get_survey_by_appointment(self, appointment_id: int) -> Optional[SurveyRow]:

        def _run() -> Optional[SurveyRow]:
            row = self.repository.get_survey_by_appointment(appointment_id)
            if row is None:
                return None
            return SurveyRow.model_validate(row)

        return await asyncio.to_thread(_run)

    # --- Plantillas ---
    async def get_templates(self, only_active: bool = False) -> list[ContractTemplateRead]:

        def _run() -> list[ContractTemplateRead]:
            rows = self.repository.get_templates(only_active)
            return [ContractTemplateRead.model_validate(r) for r in rows]

        return await asyncio.to_thread(_run)

    async def get_template_by_id(self, template_id: int) -> Optional[ContractTemplateRead]:

        def _run() -> Optional[ContractTemplateRead]:
            t = self.repository.get_template_by_id(template_id)
            if t is None:
                return None
            return ContractTemplateRead.model_validate(t)

        return await asyncio.to_thread(_run)

    async def create_template(self, data: ContractTemplateCreate) -> int:
        return await asyncio.to_thread(self.repository.create_template, data.to_domain())

    async def update_template(self, template_id: int, data: ContractTemplateUpdate) -> None:
        return await asyncio.to_thread(self.repository.update_template, template_id, data.to_domain())

    async def delete_template(self, template_id: int) -> None:
        return await asyncio.to_thread(self.repository.delete_template, template_id)

    async def get_financial_report(
        self, start_date: str, end_date: str
    ) -> list[FinancialReportRow]:

        def _run() -> list[FinancialReportRow]:
            rows = self.repository.get_detailed_report(start_date, end_date)
            return [FinancialReportRow.model_validate(r) for r in rows]

        return await asyncio.to_thread(_run)

    async def list_appointments(self) -> list[AppointmentListItem]:

        def _run() -> list[AppointmentListItem]:
            rows = self.repository.get_all()
            return [AppointmentListItem.model_validate(r) for r in rows]

        return await asyncio.to_thread(_run)

    async def list_surveys(self) -> list[SurveyRow]:

        def _run() -> list[SurveyRow]:
            rows = self.repository.get_surveys()
            return [SurveyRow.model_validate(r) for r in rows]

        return await asyncio.to_thread(_run)

    # --- Clientes ---
    async def create_customer(self, data: CustomerCreate) -> int:

        def _run() -> int:
            try:
                with self.repository.db.transaction() as conn:
                    return self.customers.insert(data, conn)
            except mysql.connector.IntegrityError as e:
                logger.warning("create_customer integrity: %s", e)
                raise ValueError("Duplicate document_number or email") from e

        return await asyncio.to_thread(_run)

    async def update_customer(self, customer_id: int, data: CustomerUpdate) -> None:

        def _run() -> None:
            with self.repository.db.transaction() as conn:
                row = self.customers.get_by_id(customer_id, conn)
                if row is None:
                    raise ValueError("Customer not found")
                self.customers.update(customer_id, data, conn)

        await asyncio.to_thread(_run)

    async def get_customer(self, customer_id: int) -> Optional[CustomerPublic]:

        def _run() -> Optional[CustomerPublic]:
            row = self.customers.get_by_id(customer_id)
            if row is None:
                return None
            return CustomerPublic.model_validate(row)

        return await asyncio.to_thread(_run)

    async def list_customers(
        self,
        *,
        limit: int,
        offset: int,
        search: Optional[str] = None,
        document_number: Optional[str] = None,
    ) -> CustomerListResponse:

        def _run() -> CustomerListResponse:
            total = self.customers.count_customers(search=search, document_number=document_number)
            rows = self.customers.list_customers(
                limit=limit, offset=offset, search=search, document_number=document_number
            )
            items = [CustomerPublic.model_validate(r) for r in rows]
            return CustomerListResponse(items=items, total=total, limit=limit, offset=offset)

        return await asyncio.to_thread(_run)

    async def soft_delete_customer(self, customer_id: int) -> None:
        row = await asyncio.to_thread(self.customers.get_by_id, customer_id)
        if row is None:
            raise ValueError("Customer not found")
        await asyncio.to_thread(self.customers.soft_delete, customer_id)

    async def _async_notify(self, event: str, payload: dict[str, object]) -> None:
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.notifier.notify, event, payload)
        except Exception as e:
            logger.warning("notify n8n failed: %s", e)
