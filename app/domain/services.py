import asyncio
import json
import logging
import math
from typing import Optional

import mysql.connector

from app.domain.contract_kinds import SurveyQuestionScope, appointment_to_contract_kind
from app.domain.models import (
    AppointmentCreate,
    ContractSign,
    Survey,
    SurveyQuestion,
)
from app.domain.survey_question_helpers import (
    QUESTION_TYPES_NEEDING_OPTIONS,
    parse_options_json,
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
from app.schemas.survey_questions import (
    SurveyQuestionCreate,
    SurveyQuestionDeletionImpact,
    SurveyQuestionRead,
    SurveyQuestionStatRow,
    SurveyQuestionUpdate,
    question_create_to_domain,
)
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
        if data.deposit > 0:
            try:
                await asyncio.to_thread(
                    self.repository.create_payment,
                    new_id,
                    float(data.deposit),
                    "Abono inicial al agendar",
                )
            except Exception:
                logger.warning("No fue posible registrar abono inicial en historial para cita id=%s", new_id)

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
        self.repository.update_status(data.appointment_id, "Finalizada")

        notification_payload: dict[str, object] = {
            "appointment_id": data.appointment_id,
            "customer_name": appointment.name,
            "phone": appointment.phone,
            "service": appointment.service,
            "health_summary": data.health_data,
        }
        asyncio.create_task(self._async_notify("contract_signed", notification_payload))

    async def list_contracts_by_customer(self, customer_id: int) -> list[dict[str, object]]:
        return await asyncio.to_thread(self.repository.get_contracts_by_customer, customer_id)

    async def get_contract(self, contract_id: int) -> Optional[dict[str, object]]:
        return await asyncio.to_thread(self.repository.get_contract_by_id, contract_id)

    def _prepare_survey_for_persist(self, data: Survey) -> Survey:
        """Valida respuestas dinámicas y rellena rating/comentarios/recomendación para la fila surveys."""
        if not data.answers:
            return data
        appt_row = self.repository.get_by_id(data.appointment_id)
        if appt_row is None:
            raise ValueError(f"Cita con ID {data.appointment_id} no encontrada")
        appt_kind = appointment_to_contract_kind(appt_row)
        rows = self.repository.list_survey_questions(include_inactive=True)
        qmap = {int(r["id"]): r for r in rows}
        ratings: list[int] = []
        texts: list[str] = []
        first_bool: Optional[bool] = None
        for ans in data.answers:
            meta = qmap.get(ans.question_id)
            if meta is None:
                raise ValueError(f"Pregunta {ans.question_id} no existe")
            ck = str(meta.get("contract_kind") or "tattoo").strip().lower()
            if ck not in ("tattoo", "piercing", "both"):
                ck = "tattoo"
            if ck != appt_kind and ck != "both":
                raise ValueError(
                    "Una o más respuestas corresponden a preguntas de otro tipo de servicio (tatuaje / piercing)."
                )
            qt = str(meta["question_type"])
            lbl = str(meta.get("label") or "")
            opts = parse_options_json(meta.get("options_json"))
            if qt == "rating_1_5":
                if ans.answer_rating is None:
                    raise ValueError(f"La pregunta «{lbl}» requiere una calificación del 1 al 5")
                ratings.append(int(ans.answer_rating))
            elif qt == "yes_no":
                if ans.answer_bool is None:
                    raise ValueError(f"La pregunta «{lbl}» requiere sí o no")
                if first_bool is None:
                    first_bool = ans.answer_bool
            elif qt == "text":
                if ans.answer_text and str(ans.answer_text).strip():
                    texts.append(str(ans.answer_text).strip())
            elif qt in ("textarea", "text_short"):
                if ans.answer_text and str(ans.answer_text).strip():
                    texts.append(str(ans.answer_text).strip())
            elif qt == "number":
                if ans.answer_number is None:
                    raise ValueError(f"La pregunta «{lbl}» requiere un valor numérico")
                num = float(ans.answer_number)
                if not math.isfinite(num):
                    raise ValueError(f"Número no válido en «{lbl}»")
                texts.append(f"{lbl}: {num}")
            elif qt in ("radio", "select"):
                if not opts:
                    raise ValueError(f"La pregunta «{lbl}» no tiene opciones configuradas")
                val = (ans.answer_text or "").strip()
                if val not in opts:
                    raise ValueError(f"Debes elegir una opción válida para «{lbl}»")
                texts.append(f"{lbl}: {val}")
            elif qt == "checkbox":
                selected: list[str] = []
                raw_t = (ans.answer_text or "").strip()
                if raw_t:
                    try:
                        parsed = json.loads(raw_t)
                        if not isinstance(parsed, list):
                            raise ValueError("lista esperada")
                        selected = [str(x).strip() for x in parsed if str(x).strip()]
                    except (json.JSONDecodeError, ValueError) as e:
                        raise ValueError(
                            f"La pregunta «{lbl}» requiere respuestas múltiples en formato lista (JSON)"
                        ) from e
                if opts:
                    for s in selected:
                        if s not in opts:
                            raise ValueError(f"Opción no válida en «{lbl}»: {s}")
                if selected:
                    texts.append(f"{lbl}: {', '.join(selected)}")
            else:
                raise ValueError(f"Tipo de pregunta no soportado: {qt}")
        rating_avg = int(round(sum(ratings) / len(ratings))) if ratings else 3
        comments = " | ".join(texts) if texts else data.comments
        would_rec = first_bool if first_bool is not None else data.would_recommend
        return Survey(
            appointment_id=data.appointment_id,
            rating=rating_avg,
            comments=comments,
            would_recommend=would_rec,
            answers=data.answers,
        )

    async def register_survey(self, data: Survey) -> int:
        prepared = await asyncio.to_thread(self._prepare_survey_for_persist, data)
        new_id = await asyncio.to_thread(self.repository.create_survey, prepared)
        if prepared.rating <= 2:
            pl: dict[str, object] = {
                "appointment_id": prepared.appointment_id,
                "rating": prepared.rating,
                "comments": prepared.comments,
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
    async def get_templates(
        self, only_active: bool = False, contract_kind: Optional[str] = None
    ) -> list[ContractTemplateRead]:

        def _run() -> list[ContractTemplateRead]:
            rows = self.repository.get_templates(only_active, contract_kind)
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

    async def update_appointment_status(
        self,
        appointment_id: int,
        status: str,
        on_cancel_abono: Optional[str] = None,
    ) -> None:
        appointment = await asyncio.to_thread(self.repository.get_by_id, appointment_id)
        if appointment is None:
            raise ValueError("Cita no encontrada")
        if status == "Cancelada":
            mode = on_cancel_abono or "credito_cliente"
            if mode not in {"credito_cliente", "devolucion"}:
                raise ValueError("Modo de anulación de abono inválido")
            await asyncio.to_thread(self.repository.cancel_appointment, appointment_id, mode)
            return
        await asyncio.to_thread(self.repository.update_status, appointment_id, status)

    async def reprogram_appointment(
        self,
        appointment_id: int,
        new_date: str,
        detail: Optional[str] = None,
    ) -> None:
        appointment = await asyncio.to_thread(self.repository.get_by_id, appointment_id)
        if appointment is None:
            raise ValueError("Cita no encontrada")
        status = str(getattr(appointment, "status", "") or "")
        if status not in {"Agendada", "Reprogramada"}:
            raise ValueError("Solo se pueden reprogramar citas en estado Agendada o Reprogramada.")
        has_contract = await asyncio.to_thread(self.repository.has_contract_for_appointment, appointment_id)
        if has_contract:
            raise ValueError("No se puede reprogramar: esta cita ya tiene contrato firmado.")
        await asyncio.to_thread(self.repository.reprogram_appointment, appointment_id, new_date, detail)

    async def update_appointment_financials(
        self,
        appointment_id: int,
        total_amount: float,
        deposit: float,
        pending_balance: float,
    ) -> None:
        appointment = await asyncio.to_thread(self.repository.get_by_id, appointment_id)
        if appointment is None:
            raise ValueError("Cita no encontrada")
        status = str(getattr(appointment, "status", "") or "")
        if status not in {"Agendada", "Reprogramada"}:
            raise ValueError("Solo puedes editar montos en citas Agendadas o Reprogramadas")
        if total_amount < 0 or deposit < 0 or pending_balance < 0:
            raise ValueError("Los valores no pueden ser negativos")
        expected = round(float(total_amount) - float(deposit), 2)
        if expected < 0:
            raise ValueError("El abono no puede ser mayor al valor total")
        if round(float(pending_balance), 2) != expected:
            raise ValueError("El saldo pendiente debe ser igual a total - abonado")
        await asyncio.to_thread(
            self.repository.update_financials,
            appointment_id,
            float(total_amount),
            float(deposit),
            float(pending_balance),
        )

    async def list_appointment_payments(self, appointment_id: int) -> list[dict[str, object]]:
        appointment = await asyncio.to_thread(self.repository.get_by_id, appointment_id)
        if appointment is None:
            raise ValueError("Cita no encontrada")
        return await asyncio.to_thread(self.repository.list_payments_by_appointment, appointment_id)

    async def add_appointment_payment(self, appointment_id: int, amount: float, note: Optional[str] = None) -> None:
        appointment = await asyncio.to_thread(self.repository.get_by_id, appointment_id)
        if appointment is None:
            raise ValueError("Cita no encontrada")
        status = str(getattr(appointment, "status", "") or "")
        if status not in {"Agendada", "Reprogramada"}:
            raise ValueError("Solo puedes agregar abonos en citas Agendadas o Reprogramadas")
        if amount <= 0:
            raise ValueError("El abono adicional debe ser mayor a cero")
        total_amount = float(getattr(appointment, "total_amount", 0) or 0)
        current_deposit = float(getattr(appointment, "deposit", 0) or 0)
        if current_deposit + amount > total_amount:
            raise ValueError("El abono adicional excede el valor total del trabajo")
        await asyncio.to_thread(self.repository.create_payment, appointment_id, float(amount), note)

    async def list_surveys(self) -> list[SurveyRow]:

        def _run() -> list[SurveyRow]:
            rows = self.repository.get_surveys()
            return [SurveyRow.model_validate(r) for r in rows]

        return await asyncio.to_thread(_run)

    async def list_survey_questions(
        self,
        *,
        include_inactive: bool = False,
        contract_kind: Optional[str] = None,
    ) -> list[SurveyQuestionRead]:

        def _run() -> list[SurveyQuestionRead]:
            ck: Optional[str] = None
            if contract_kind is not None and str(contract_kind).strip():
                v = str(contract_kind).strip().lower()
                if v not in ("tattoo", "piercing", "both"):
                    raise ValueError("contract_kind debe ser tattoo, piercing o both")
                ck = v
            rows = self.repository.list_survey_questions(
                include_inactive=include_inactive,
                contract_kind=ck,
            )
            return [SurveyQuestionRead.model_validate(r) for r in rows]

        return await asyncio.to_thread(_run)

    async def create_survey_question(self, data: SurveyQuestionCreate) -> int:
        domain = question_create_to_domain(data)
        return await asyncio.to_thread(self.repository.create_survey_question, domain)

    async def update_survey_question(self, question_id: int, data: SurveyQuestionUpdate) -> None:

        def _run() -> None:
            row = self.repository.get_survey_question(question_id)
            if row is None:
                raise ValueError("Pregunta no encontrada")
            merged_type = str(data.question_type) if data.question_type is not None else str(row["question_type"])
            if merged_type in QUESTION_TYPES_NEEDING_OPTIONS:
                if data.options is not None:
                    merged_opts = list(data.options) if data.options else None
                else:
                    merged_opts = parse_options_json(row.get("options_json"))
                if not merged_opts or len(merged_opts) < 2:
                    raise ValueError("Este tipo requiere al menos 2 opciones en `options`")
                opts_for_domain: Optional[list[str]] = merged_opts
            else:
                if data.options is not None and data.options:
                    raise ValueError("Este tipo de pregunta no admite lista de opciones")
                opts_for_domain = None
            if data.contract_kind is not None:
                merged_ck = str(data.contract_kind).strip().lower()
            else:
                merged_ck = str(row.get("contract_kind") or "tattoo").strip().lower()
            if merged_ck not in ("tattoo", "piercing", "both"):
                merged_ck = "tattoo"
            merged = SurveyQuestion(
                id=question_id,
                label=str(data.label) if data.label is not None else str(row["label"]),
                question_type=merged_type,
                options=opts_for_domain,
                sort_order=int(data.sort_order) if data.sort_order is not None else int(row.get("sort_order") or 0),
                contract_kind=merged_ck,
                is_active=bool(data.is_active) if data.is_active is not None else bool(row.get("is_active", True)),
            )
            self.repository.update_survey_question(merged)

        return await asyncio.to_thread(_run)

    async def delete_survey_question(self, question_id: int) -> None:

        def _run() -> None:
            row = self.repository.get_survey_question(question_id)
            if row is None:
                raise ValueError("Pregunta no encontrada")
            self.repository.delete_survey_question(question_id)

        return await asyncio.to_thread(_run)

    async def survey_question_deletion_impact(self, question_id: int) -> SurveyQuestionDeletionImpact:

        def _run() -> SurveyQuestionDeletionImpact:
            row = self.repository.get_survey_question(question_id)
            if row is None:
                raise ValueError("Pregunta no encontrada")
            n = self.repository.count_survey_answers_for_question(question_id)
            return SurveyQuestionDeletionImpact(
                question_id=question_id,
                label=str(row["label"]),
                registered_answers=n,
            )

        return await asyncio.to_thread(_run)

    async def survey_question_stats_summary(self) -> list[SurveyQuestionStatRow]:

        def _run() -> list[SurveyQuestionStatRow]:
            rows = self.repository.get_survey_question_stats_summary()
            out: list[SurveyQuestionStatRow] = []
            for r in rows:
                ar = r.get("avg_rating")
                avg = float(ar) if ar is not None else None
                yc = r.get("yes_count")
                nc = r.get("no_count")
                tc = r.get("text_response_count")
                an = r.get("avg_number")
                ck_stat = str(r.get("contract_kind") or "tattoo").strip().lower()
                if ck_stat not in ("tattoo", "piercing", "both"):
                    ck_stat = "tattoo"
                row_ck: SurveyQuestionScope = (
                    "piercing" if ck_stat == "piercing" else ("both" if ck_stat == "both" else "tattoo")
                )
                rb = r.get("rating_breakdown")
                nb = r.get("number_breakdown")
                cb = r.get("choice_breakdown")
                rating_bd: Optional[dict[str, int]] = None
                if isinstance(rb, dict) and rb:
                    rating_bd = {str(k): int(v) for k, v in rb.items()}
                number_bd: Optional[dict[str, int]] = None
                if isinstance(nb, dict) and nb:
                    number_bd = {str(k): int(v) for k, v in nb.items()}
                choice_bd: Optional[dict[str, int]] = None
                if isinstance(cb, dict) and cb:
                    choice_bd = {str(k): int(v) for k, v in cb.items()}
                out.append(
                    SurveyQuestionStatRow(
                        question_id=int(r["question_id"]),
                        label=str(r["label"]),
                        question_type=str(r["question_type"]),
                        sort_order=int(r.get("sort_order") or 0),
                        contract_kind=row_ck,
                        is_active=bool(r.get("is_active", True)),
                        response_count=int(r.get("response_count") or 0),
                        avg_rating=avg,
                        yes_count=int(yc) if yc is not None else None,
                        no_count=int(nc) if nc is not None else None,
                        text_response_count=int(tc) if tc is not None else None,
                        avg_number=float(an) if an is not None else None,
                        rating_breakdown=rating_bd,
                        number_breakdown=number_bd,
                        choice_breakdown=choice_bd,
                    )
                )
            return out

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
