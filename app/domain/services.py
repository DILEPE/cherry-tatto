import asyncio
import base64
import json
import logging
import math
from datetime import datetime, date
from typing import Any, Optional

import mysql.connector

from app.domain.contract_kinds import (
    SurveyQuestionScope,
    appointment_to_contract_kind,
    service_type_to_assignee_panel_role,
    service_type_to_contract_kind,
)
from app.domain.contract_signing_guard import appointment_must_be_fully_paid_for_contract
from app.domain.piercing_procedure_labels import (
    build_piercing_type_index,
    expand_procedure_answer_candidates,
    resolve_piercing_type_canonical,
)
from app.domain.procedure_consent import PROCEDURE_CONSENT_SURVEY_QUESTION_ID
from app.domain.service_types import resolve_service_type
from app.domain.models import (
    AppointmentCreate,
    ContractSign,
    Survey,
    SurveyQuestion,
)
from app.schemas.contract import _is_non_empty_signature_blob
from app.domain.panel_user_profile import PANEL_ROLE_LABEL_ES
from app.domain.panel_modules import ASSIGNABLE_PANEL_MODULE_KEYS
from app.domain.panel_passwords import hash_password, verify_password
from app.domain.payment_receipt_pdf import (
    PAYMENT_RECEIPT_N8N_TEMPLATE_KEY,
    PaymentReceiptPdfContext,
    build_payment_receipt_pdf,
)
from app.domain.survey_question_helpers import (
    QUESTION_TYPES_NEEDING_OPTIONS,
    parse_options_json,
)
from app.schemas.appointment import (
    AppointmentListItem,
    AppointmentPaymentPatchRequest,
    AppointmentSearchHit,
    AppointmentSearchResponse,
)
from app.schemas.customer import (
    CustomerCreate,
    CustomerListResponse,
    CustomerPublic,
    CustomerUpdate,
)
from app.schemas.panel_user import (
    PanelUserAssignable,
    PanelUserCreate,
    PanelUserModulesBody,
    PanelUserPublic,
    PanelUserRegister,
    PanelUserSessionPublic,
    PanelUserUpdate,
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
from app.schemas.store import StoreCreate, StorePublic, StoreUpdate
from app.schemas.template import ContractTemplateCreate, ContractTemplateRead, ContractTemplateUpdate

logger = logging.getLogger(__name__)


class BusinessLogicService:
    """
    Capa de dominio / aplicación: orquesta citas, clientes, plantillas y notificaciones.
    """

    def __init__(
        self,
        appointment_repository,
        customer_repository,
        notifier,
        panel_user_repository=None,
        store_repository=None,
    ):
        self.repository = appointment_repository
        self.customers = customer_repository
        self.notifier = notifier
        self.panel_user_repo = panel_user_repository
        self.store_repo = store_repository

    def _payment_receipt_pdf_webhook_payload(
        self,
        *,
        appointment_id: int,
        receipt_id: int,
        customer_id: Optional[int],
        customer_name: str,
        phone: str,
        kind: str,
        appointment_payment_id: Optional[int],
        amount: float,
        payment_note: str,
        file_name: str,
        pdf_bytes: bytes,
    ) -> dict[str, object]:
        """Payload único para `payment_receipt_pdf` → n8n (sustituye al PDF tipo «recibo Cherry» anterior)."""
        return {
            "appointment_id": appointment_id,
            "receipt_id": receipt_id,
            "customer_id": customer_id,
            "customer_name": customer_name,
            "phone": phone,
            "kind": kind,
            "appointment_payment_id": appointment_payment_id,
            "amount": amount,
            "payment_note": payment_note,
            "file_name": file_name,
            "mime_type": "application/pdf",
            "pdf_template": PAYMENT_RECEIPT_N8N_TEMPLATE_KEY,
            "pdf_base64": base64.standard_b64encode(pdf_bytes).decode("ascii"),
        }

    def _schedule_n8n_notify(self, event: str, payload: dict[str, object]) -> None:
        """Programa `_async_notify` y registra fallos (create_task oculta excepciones si no se espera la tarea)."""

        async def _runner() -> None:
            try:
                await self._async_notify(event, payload)
            except Exception:
                logger.exception("Fallo al notificar n8n en segundo plano (event=%s)", event)

        asyncio.create_task(_runner())

    def _resolve_receipt_client_fields(
        self,
        appt: Any,
        *,
        field_overrides: Optional[dict[str, str]] = None,
    ) -> dict[str, str]:
        """Nombre, teléfono, fecha/hora de cita y correo para el PDF (cita + cliente + overrides)."""
        ov = field_overrides or {}

        client_name = str(getattr(appt, "name", "") or "").strip()
        client_phone = str(getattr(appt, "phone", "") or "").strip()
        appointment_when = str(getattr(appt, "date", "") or "").strip()
        email_s = str(getattr(appt, "customer_email", "") or "").strip()

        raw_cust = getattr(appt, "customer_id", None)
        customer_id = int(raw_cust) if raw_cust is not None else None
        if customer_id is not None and (not client_name or not client_phone or not email_s):
            crow = self.customers.get_by_id(int(customer_id))
            if crow:
                if not email_s:
                    email_s = str(crow.get("email") or "").strip()
                if not client_name:
                    fn = str(crow.get("first_name") or "").strip()
                    ln = str(crow.get("last_name") or "").strip()
                    client_name = f"{fn} {ln}".strip()
                if not client_phone:
                    client_phone = str(crow.get("phone_number") or "").strip()

        on = str(ov.get("client_name") or ov.get("name") or "").strip()
        op = str(ov.get("client_phone") or ov.get("phone") or "").strip()
        od = str(ov.get("appointment_when") or ov.get("date") or "").strip()
        oe = str(ov.get("client_email") or ov.get("email") or "").strip()
        if on:
            client_name = on
        if op:
            client_phone = op
        if od:
            appointment_when = od
        if oe:
            email_s = oe

        return {
            "client_name": client_name,
            "client_phone": client_phone,
            "appointment_when": appointment_when,
            "client_email": email_s,
        }

    def _issue_payment_receipt(
        self,
        appointment_id: int,
        *,
        kind: str,
        appointment_payment_id: Optional[int],
        receipt_amount: float,
        payment_note: Optional[str],
        field_overrides: Optional[dict[str, str]] = None,
    ) -> tuple[Optional[int], Optional[bytes], Optional[str]]:
        """Genera PDF y lo guarda en `appointment_payment_receipts`. Ejecutar en worker thread.

        Devuelve ``(receipt_id, pdf_bytes, file_name)`` o ``(None, None, None)`` si falla la cita.
        """
        if float(receipt_amount or 0) <= 0:
            return None, None, None
        get_row = getattr(self.repository, "get_row_for_payment_receipt", None)
        if callable(get_row):
            appt = get_row(appointment_id)
        else:
            appt = self.repository.get_by_id(appointment_id)
        if appt is None:
            return None, None, None
        raw_cust = getattr(appt, "customer_id", None)
        customer_id = int(raw_cust) if raw_cust is not None else None
        kind_label = "Abono adicional" if kind == "abono" else "Agendamiento / primer abono"

        rows_pay = self.repository.list_payments_by_appointment(appointment_id)
        payment_history: list[tuple[float, Optional[str]]] = [
            (float(r["amount"]), str(r["note"]).strip() if r.get("note") else None) for r in rows_pay
        ]

        fields = self._resolve_receipt_client_fields(appt, field_overrides=field_overrides)

        ctx = PaymentReceiptPdfContext(
            appointment_id=int(appointment_id),
            client_name=fields["client_name"],
            client_phone=fields["client_phone"],
            appointment_when=fields["appointment_when"],
            service=str(getattr(appt, "service", "") or ""),
            detail=str(getattr(appt, "detail", "") or ""),
            total_amount=float(getattr(appt, "total_amount", 0) or 0),
            this_payment=float(receipt_amount),
            deposit_total_after=float(getattr(appt, "deposit", 0) or 0),
            pending_after=float(getattr(appt, "pending_balance", 0) or 0),
            kind_label=kind_label,
            issued_at=datetime.now(),
            payment_note=payment_note,
            client_email=fields["client_email"],
            payment_history=payment_history,
        )
        try:
            pdf_bytes = build_payment_receipt_pdf(ctx)
        except Exception:
            logger.exception(
                "Fallo al generar orden de trabajo PDF (cita id=%s). Comprueba pymupdf.",
                appointment_id,
            )
            return None, None, None
        file_name = f"orden_trabajo_cita_{appointment_id}_{int(datetime.now().timestamp() * 1000)}.pdf"
        linked_pay_id: Optional[int] = None
        if appointment_payment_id is not None:
            try:
                linked_pay_id = int(appointment_payment_id)
            except (TypeError, ValueError):
                linked_pay_id = None
        if not linked_pay_id or linked_pay_id <= 0:
            linked_pay_id = self._resolve_payment_id_for_receipt(
                appointment_id,
                amount=float(receipt_amount),
                payment_note=payment_note,
                kind=kind,
            )
        rid = self.repository.insert_payment_receipt(
            appointment_id,
            customer_id,
            linked_pay_id,
            kind,
            float(receipt_amount),
            float(ctx.total_amount),
            float(ctx.deposit_total_after),
            float(ctx.pending_after),
            payment_note,
            file_name,
            pdf_bytes,
        )
        if not rid:
            return None, None, None
        if linked_pay_id and linked_pay_id > 0 and (
            not appointment_payment_id or int(appointment_payment_id) <= 0
        ):
            link_fn = getattr(self.repository, "link_payment_receipt_to_payment", None)
            if callable(link_fn):
                try:
                    link_fn(int(rid), int(appointment_id), int(linked_pay_id))
                except Exception:
                    logger.warning(
                        "No se pudo vincular recibo %s al abono %s (cita %s)",
                        rid,
                        linked_pay_id,
                        appointment_id,
                        exc_info=True,
                    )
        return int(rid), pdf_bytes, file_name

    def _resolve_payment_id_for_receipt(
        self,
        appointment_id: int,
        *,
        amount: float,
        payment_note: Optional[str],
        kind: str,
    ) -> Optional[int]:
        """Busca el id de appointment_payments que corresponde a este recibo."""
        note_l = (payment_note or "").strip().lower()
        want_inicial = kind == "inicial" or "inicial" in note_l
        rows = self.repository.list_payments_by_appointment(appointment_id)
        matches: list[int] = []
        for row in rows:
            try:
                pid = int(row.get("id") or 0)
            except (TypeError, ValueError):
                continue
            if pid <= 0:
                continue
            try:
                row_amt = float(row.get("amount") or 0)
            except (TypeError, ValueError):
                continue
            if abs(row_amt - float(amount)) >= 0.01:
                continue
            rnote = str(row.get("note") or "").strip().lower()
            if want_inicial and "inicial" in rnote:
                matches.append(pid)
            elif not want_inicial and "inicial" not in rnote:
                matches.append(pid)
            elif want_inicial and not rnote:
                matches.append(pid)
        if len(matches) == 1:
            return matches[0]
        if len(rows) == 1:
            try:
                only = int(rows[0].get("id") or 0)
            except (TypeError, ValueError):
                return None
            return only if only > 0 else None
        return None

    def _ensure_initial_payment_ledger_id(self, appointment_id: int, amount: float) -> Optional[int]:
        """Fila en appointment_payments para el abono al agendar (sin duplicar deposit en cita)."""
        note = "Abono inicial al agendar"
        try:
            pid = self.repository.insert_payment_ledger_row_only(appointment_id, float(amount), note)
            if pid > 0:
                return int(pid)
        except Exception:
            logger.warning(
                "No se pudo insertar abono inicial en historial (cita id=%s); se reutiliza fila existente si hay.",
                appointment_id,
                exc_info=True,
            )
        resolved = self._resolve_payment_id_for_receipt(
            appointment_id, amount=float(amount), payment_note=note, kind="inicial"
        )
        if resolved:
            return resolved
        try:
            pid = self.repository.insert_payment_ledger_row_only(appointment_id, float(amount), note)
            return int(pid) if pid > 0 else None
        except Exception:
            logger.exception(
                "Fallo definitivo al registrar abono inicial en historial (cita id=%s)",
                appointment_id,
            )
            return None

    # --- Citas + cliente ---

    async def register_appointment(self, data: AppointmentCreate) -> tuple[int, Optional[int]]:
        """
        Crea cita. Si viene `customer` (dict), valida con Pydantic y hace upsert por documento.
        Si viene `customer_id`, verifica existencia. Usa transacción para cliente + cita.

        Recibo PDF inicial: si el abono al agendar es **estrictamente mayor que cero** (cualquier servicio).

        Si el abono es 0: sin movimiento en historial ni webhook `payment_receipt_pdf`.
        """
        resolved_type = resolve_service_type(data.service)

        def _pre_validate() -> None:
            if data.assigned_panel_user_id is None:
                raise ValueError("Debes asignar un tatuador o perforador a la cita.")
            if self.panel_user_repo is None:
                return
            row = self.panel_user_repo.get_by_id(int(data.assigned_panel_user_id))
            if not row or not row.get("is_active", True):
                raise ValueError("El profesional asignado no existe o está inactivo.")
            need = service_type_to_assignee_panel_role(resolved_type)
            if str(row.get("role") or "") != need:
                raise ValueError(
                    f"Para este tipo de servicio debes elegir un profesional con rol "
                    f"«{PANEL_ROLE_LABEL_ES.get(need, need)}»."
                )

        await asyncio.to_thread(_pre_validate)

        dep_round = max(0.0, round(float(data.deposit or 0), 2))
        tot_round = max(0.0, round(float(data.total_amount or 0), 2))
        pend_round = max(0.0, round(tot_round - dep_round, 2))
        data.deposit = dep_round
        data.total_amount = tot_round
        data.pending_balance = pend_round

        def _sync_register() -> tuple[int, Optional[int]]:
            with self.repository.db.transaction() as conn:
                resolved_id: Optional[int] = data.customer_id
                if data.customer_id is not None:
                    cid = int(data.customer_id)
                    row = self.customers.get_by_id(cid, conn)
                    if row is None:
                        raise ValueError(f"Cliente id={cid} no encontrado.")
                    resolved_id = cid
                    if data.customer is not None:
                        c = CustomerCreate.model_validate(data.customer)
                        doc_existing = str(row.get("document_number") or "").strip()
                        if str(c.document_number).strip() != doc_existing:
                            raise ValueError(
                                "El documento enviado no coincide con el cliente vinculado a la cita."
                            )
                        self.customers.update(cid, CustomerUpdate(**c.model_dump()), conn)
                elif data.customer is not None:
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
        deposit_amt = float(data.deposit or 0)
        initial_pay_id: Optional[int] = None
        if deposit_amt > 0:
            initial_pay_id = await asyncio.to_thread(
                self._ensure_initial_payment_ledger_id, new_id, deposit_amt
            )
        receipt_out: tuple[Optional[int], Optional[bytes], Optional[str]] = (None, None, None)
        if deposit_amt > 0:
            try:
                creation_snapshot = {
                    "client_name": str(data.name or "").strip(),
                    "client_phone": str(data.phone or "").strip(),
                    "appointment_when": str(data.date or "").strip(),
                }
                receipt_out = await asyncio.to_thread(
                    lambda snap=creation_snapshot: self._issue_payment_receipt(
                        new_id,
                        kind="inicial",
                        appointment_payment_id=initial_pay_id,
                        receipt_amount=deposit_amt,
                        payment_note="Abono inicial al agendar",
                        field_overrides=snap,
                    )
                )
            except Exception:
                logger.exception("No se pudo emitir recibo inicial para cita id=%s", new_id)
                receipt_out = (None, None, None)

        rid, pdf_b, fname = receipt_out
        queued_initial_receipt_pdf = False
        if rid and pdf_b and deposit_amt > 0 and len(pdf_b) > 0:
            receipt_payload = self._payment_receipt_pdf_webhook_payload(
                appointment_id=new_id,
                receipt_id=rid,
                customer_id=customer_id,
                customer_name=str(data.name or ""),
                phone=str(data.phone or ""),
                kind="inicial",
                appointment_payment_id=initial_pay_id,
                amount=deposit_amt,
                payment_note="Abono inicial al agendar",
                file_name=fname or "orden_trabajo.pdf",
                pdf_bytes=pdf_b,
            )
            self._schedule_n8n_notify("payment_receipt_pdf", receipt_payload)
            queued_initial_receipt_pdf = True

        payload: dict[str, object] = {
            "id": new_id,
            "name": data.name,
            "phone": data.phone,
            "service": data.service,
            "date": data.date,
            "customer_id": customer_id,
            "deposit": float(data.deposit or 0),
            "total_amount": float(data.total_amount or 0),
            "pending_balance": float(data.pending_balance or 0),
            "payment_receipt_pdf_webhook_enqueued": queued_initial_receipt_pdf,
        }
        asyncio.create_task(self._async_notify("appointment_created", payload))
        return new_id, customer_id

    async def process_contract_signature(self, data: ContractSign) -> None:
        appointment = self.repository.get_by_id(data.appointment_id)
        if not appointment:
            raise ValueError(f"Cita con ID {data.appointment_id} no encontrada.")

        ok_pay, pay_err = appointment_must_be_fully_paid_for_contract(
            total_amount=getattr(appointment, "total_amount", None),
            deposit=getattr(appointment, "deposit", None),
            pending_balance=getattr(appointment, "pending_balance", None),
        )
        if not ok_pay:
            raise ValueError(
                pay_err or "La cita no cumple las condiciones de pago para firmar el contrato."
            )

        if self.repository.has_contract_for_appointment(data.appointment_id):
            raise ValueError(
                "Ya existe un contrato registrado para esta cita. Si falta la firma del profesional, "
                "complétela desde la agenda con «Completar firma del profesional»."
            )

        self.repository.create_contract(data)

        if _is_non_empty_signature_blob(data.artist_signature):
            self.repository.update_status(data.appointment_id, "Finalizada")

        notification_payload: dict[str, object] = {
            "appointment_id": data.appointment_id,
            "customer_name": appointment.name,
            "phone": appointment.phone,
            "service": appointment.service,
            "health_summary": data.health_data,
        }
        asyncio.create_task(self._async_notify("contract_signed", notification_payload))

        consent_pdf_payload = await asyncio.to_thread(
            self._build_contract_consent_pdf_payload,
            data.appointment_id,
            appointment,
        )
        if consent_pdf_payload:
            asyncio.create_task(self._async_notify("contract_consent_pdf", consent_pdf_payload))

    async def get_contract_latest_summary_for_appointment(self, appointment_id: int) -> Optional[dict[str, object]]:
        """Texto del contrato y si falta firma del profesional (sin devolver blobs completos)."""

        def _load() -> Optional[dict[str, object]]:
            row = self.repository.get_latest_contract_row_for_appointment(appointment_id)
            if not row:
                return None
            return {
                "contract_id": int(row["id"]),
                "appointment_id": int(row["appointment_id"]),
                "contract_text": str(row.get("contract_text") or ""),
                "pending_artist_signature": not _is_non_empty_signature_blob(row.get("artist_signature")),
            }

        return await asyncio.to_thread(_load)

    async def complete_contract_artist_signature(self, appointment_id: int, artist_signature: str) -> None:
        """Registra la firma del tatuador/perforador y cierra la cita cuando ya firmó el cliente."""
        if not _is_non_empty_signature_blob(artist_signature):
            raise ValueError(
                "La firma del profesional es obligatoria: debe dibujarse en el recuadro (o modo texto si aplica)."
            )
        appointment = self.repository.get_by_id(appointment_id)
        if not appointment:
            raise ValueError(f"Cita con ID {appointment_id} no encontrada.")

        ok_pay, pay_err = appointment_must_be_fully_paid_for_contract(
            total_amount=getattr(appointment, "total_amount", None),
            deposit=getattr(appointment, "deposit", None),
            pending_balance=getattr(appointment, "pending_balance", None),
        )
        if not ok_pay:
            raise ValueError(
                pay_err or "La cita no cumple las condiciones de pago para completar el contrato."
            )

        row = self.repository.get_latest_contract_row_for_appointment(appointment_id)
        if not row:
            raise ValueError("No hay contrato registrado para esta cita.")
        if _is_non_empty_signature_blob(row.get("artist_signature")):
            raise ValueError("El contrato ya tiene la firma del profesional.")

        self.repository.update_contract_artist_signature(int(row["id"]), artist_signature)
        self.repository.update_status(appointment_id, "Finalizada")

    def _resolve_piercing_procedure_label(
        self, appointment_id: int, preferred_answer: Optional[str]
    ) -> Optional[str]:
        """
        Etiqueta para `procedure_consent_documents`: primero la pregunta fija (id configurado),
        luego cualquier respuesta de encuesta cuyo texto coincida (exacto o sin distinguir mayúsculas).
        Así se envía el PDF de cuidados aunque la pregunta de procedimiento no sea la id=3 o venga en checkbox.
        """
        index = build_piercing_type_index(
            consent_labels=self.repository.list_procedure_consent_labels()
        )

        def match_piece(piece: str) -> Optional[str]:
            canonical = resolve_piercing_type_canonical(piece, index)
            if not canonical:
                return None
            row = self.repository.get_procedure_consent_document(canonical)
            if row is not None:
                sl = row.get("survey_option_label")
                return str(sl).strip() if sl else canonical
            return canonical

        for cand in expand_procedure_answer_candidates(preferred_answer or ""):
            got = match_piece(cand)
            if got:
                return got

        for raw in self.repository.list_survey_answer_texts_for_appointment(appointment_id):
            for cand in expand_procedure_answer_candidates(raw):
                got = match_piece(cand)
                if got:
                    return got
        return None

    def _build_contract_consent_pdf_payload(
        self, appointment_id: int, appointment: Any
    ) -> Optional[dict[str, object]]:
        """PDF de consentimiento según tipo de cita y respuesta de encuesta (pregunta id fija)."""
        kind = appointment_to_contract_kind(appointment)
        if kind == "tattoo":
            label = "Tatuaje"
        else:
            ans = self.repository.get_survey_answer_text(
                appointment_id, PROCEDURE_CONSENT_SURVEY_QUESTION_ID
            )
            label = self._resolve_piercing_procedure_label(int(appointment_id), ans)
            if not label:
                logger.warning(
                    "Contrato piercing firmado sin respuesta reconocible para PDF de consentimiento/cuidados "
                    "(pregunta %s ni ningún texto en survey_answers coincide con procedure_consent_documents). "
                    "cita=%s",
                    PROCEDURE_CONSENT_SURVEY_QUESTION_ID,
                    appointment_id,
                )
                return None
        row = self.repository.get_procedure_consent_document(label)
        if row is None:
            logger.warning(
                "No hay fila en procedure_consent_documents para %r (cita %s).",
                label,
                appointment_id,
            )
            return None
        raw_b64 = row.get("pdf_base64")
        if not isinstance(raw_b64, str) or not raw_b64.strip():
            return None
        fname = str(row.get("source_filename") or "").strip() or f"{label}.pdf"
        return {
            "appointment_id": appointment_id,
            "procedure_label": label,
            "contract_kind": kind,
            "customer_name": str(getattr(appointment, "name", "") or ""),
            "phone": str(getattr(appointment, "phone", "") or ""),
            "service": str(getattr(appointment, "service", "") or ""),
            "file_name": fname,
            "mime_type": "application/pdf",
            "pdf_base64": raw_b64.strip(),
        }

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

    async def list_appointments(
        self, assigned_panel_user_id: Optional[int] = None
    ) -> list[AppointmentListItem]:

        def _run() -> list[AppointmentListItem]:
            rows = self.repository.get_all(assigned_panel_user_id=assigned_panel_user_id)
            return [AppointmentListItem.model_validate(r) for r in rows]

        return await asyncio.to_thread(_run)

    async def search_appointments(
        self,
        *,
        field: str,
        term: str,
        limit: int = 10,
        offset: int = 0,
        assigned_panel_user_id: Optional[int] = None,
    ) -> AppointmentSearchResponse:
        def _run() -> AppointmentSearchResponse:
            try:
                rows, total = self.repository.search_appointments(
                    field=field,
                    term=term,
                    limit=limit,
                    offset=offset,
                    assigned_panel_user_id=assigned_panel_user_id,
                )
            except ValueError as e:
                code = str(e)
                if code in ("SEARCH_TERM_EMPTY", "SEARCH_FIELD_INVALID"):
                    raise ValueError(code) from e
                raise
            items = [AppointmentSearchHit.model_validate(r) for r in rows]
            return AppointmentSearchResponse(
                items=items,
                total=int(total),
                limit=max(1, min(int(limit), 50)),
                offset=max(0, int(offset)),
            )

        return await asyncio.to_thread(_run)

    async def work_performed_labels_for_appointments(
        self, appointment_ids: list[int]
    ) -> dict[int, str]:
        """Etiquetas de perforación (encuesta) para citas piercing; clave = appointment_id."""

        def _run() -> dict[int, str]:
            from app.domain.procedure_consent import PROCEDURE_CONSENT_SURVEY_QUESTION_ID
            from app.domain.work_performed_label import resolve_work_performed_from_survey_raw

            index = build_piercing_type_index(
                consent_labels=self.repository.list_procedure_consent_labels()
            )
            raw = self.repository.get_piercing_type_labels_by_appointment_ids(
                appointment_ids,
                question_id=PROCEDURE_CONSENT_SURVEY_QUESTION_ID,
            )
            out: dict[int, str] = {}
            for appt_id, text in raw.items():
                label = resolve_work_performed_from_survey_raw(text, index)
                if label:
                    out[int(appt_id)] = label
            return out

        return await asyncio.to_thread(_run)

    async def get_appointment_detail(self, appointment_id: int) -> AppointmentListItem:

        def _run() -> AppointmentListItem:
            row = self.repository.get_appointment_list_row(appointment_id)
            if row is None:
                raise ValueError("Cita no encontrada")
            return AppointmentListItem.model_validate(row)

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

    async def patch_appointment_meta_details(
        self,
        appointment_id: int,
        *,
        assigned_panel_user_id: Optional[int],
        is_priority: bool,
        detail: Optional[str],
    ) -> None:
        appointment = await asyncio.to_thread(self.repository.get_by_id, appointment_id)
        if appointment is None:
            raise ValueError("Cita no encontrada")
        status = str(getattr(appointment, "status", "") or "")
        if status not in {"Agendada", "Reprogramada"}:
            raise ValueError("Solo puedes editar estos datos en citas Agendadas o Reprogramadas")
        if assigned_panel_user_id is not None:
            has_signed = await asyncio.to_thread(self.repository.has_contract_for_appointment, appointment_id)
            if has_signed:
                raise ValueError("No se puede cambiar el artista cuando la cita ya tiene contrato firmado.")
            pu = await asyncio.to_thread(self.panel_user_repo.get_by_id, int(assigned_panel_user_id))
            if pu is None:
                raise ValueError("Usuario del panel del artista no encontrado")
        dnorm: Optional[str] = None
        if detail is not None:
            dnorm = detail.strip()

        await asyncio.to_thread(
            self.repository.patch_appointment_meta,
            appointment_id,
            is_priority=is_priority,
            assigned_panel_user_id=assigned_panel_user_id,
            detail=dnorm,
        )

    async def list_appointment_payments(self, appointment_id: int) -> list[dict[str, object]]:
        appointment = await asyncio.to_thread(self.repository.get_by_id, appointment_id)
        if appointment is None:
            raise ValueError("Cita no encontrada")
        return await asyncio.to_thread(self.repository.list_payments_by_appointment, appointment_id)

    async def add_appointment_payment(
        self,
        appointment_id: int,
        amount: float,
        note: Optional[str] = None,
        paid_on: Optional[date] = None,
    ) -> int:
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

        def _pay() -> int:
            return self.repository.create_payment(
                appointment_id,
                float(amount),
                note,
                paid_on,
            )

        pay_id = await asyncio.to_thread(_pay)
        try:
            receipt_out = await asyncio.to_thread(
                lambda: self._issue_payment_receipt(
                    appointment_id,
                    kind="abono",
                    appointment_payment_id=pay_id,
                    receipt_amount=float(amount),
                    payment_note=note,
                )
            )
        except Exception:
            logger.exception("No se pudo emitir recibo de abono para cita id=%s pago id=%s", appointment_id, pay_id)
            receipt_out = (None, None, None)

        rid, pdf_b, fname = receipt_out
        if rid and pdf_b and len(pdf_b) > 0:
            raw_cust = getattr(appointment, "customer_id", None)
            cid_pdf = int(raw_cust) if raw_cust is not None else None
            receipt_payload = self._payment_receipt_pdf_webhook_payload(
                appointment_id=appointment_id,
                receipt_id=rid,
                customer_id=cid_pdf,
                customer_name=str(getattr(appointment, "name", "") or ""),
                phone=str(getattr(appointment, "phone", "") or ""),
                kind="abono",
                appointment_payment_id=pay_id,
                amount=float(amount),
                payment_note=note or "",
                file_name=fname or "orden_trabajo.pdf",
                pdf_bytes=pdf_b,
            )
            self._schedule_n8n_notify("payment_receipt_pdf", receipt_payload)
        return pay_id

    async def patch_appointment_payment_row(
        self, appointment_id: int, payment_id: int, data: AppointmentPaymentPatchRequest
    ) -> None:
        row = await asyncio.to_thread(self.repository.get_payment_by_id, payment_id)
        if not row:
            raise ValueError("Abono no encontrado")
        if int(row.get("appointment_id") or 0) != int(appointment_id):
            raise ValueError("El abono no pertenece a esta cita")
        appointment = await asyncio.to_thread(self.repository.get_by_id, appointment_id)
        if appointment is None:
            raise ValueError("Cita no encontrada")
        status = str(getattr(appointment, "status", "") or "")
        if status not in {"Agendada", "Reprogramada"}:
            raise ValueError("Solo puedes editar abonos en citas Agendadas o Reprogramadas")
        total_amount = float(getattr(appointment, "total_amount", 0) or 0)
        old_amt = float(row.get("amount") or 0)
        amt_new = float(data.amount) if data.amount is not None else old_amt
        payments = await asyncio.to_thread(self.repository.list_payments_by_appointment, appointment_id)
        s = 0.0
        for p in payments:
            pid = int(p.get("id") or 0)
            a = float(p.get("amount") or 0)
            if pid == int(payment_id):
                s += amt_new
            else:
                s += a
        if round(s, 2) > round(total_amount, 2) + 0.005:
            raise ValueError("La suma de abonos excede el valor total del trabajo.")

        note_kw: Any = "__NO_NOTE_CHANGE__"
        paid_kw: Any = "__NO_PAID_CHANGE__"
        if "note" in data.model_fields_set:
            note_kw = data.note
        if "paid_on" in data.model_fields_set:
            paid_kw = data.paid_on

        def _patch() -> int:
            return self.repository.patch_payment_row(
                int(payment_id),
                amount=data.amount,
                note=note_kw,
                paid_on=paid_kw,
            )

        await asyncio.to_thread(_patch)

    async def list_appointment_payment_receipts(self, appointment_id: int) -> list[dict[str, object]]:
        appointment = await asyncio.to_thread(self.repository.get_by_id, appointment_id)
        if appointment is None:
            raise ValueError("Cita no encontrada")
        return await asyncio.to_thread(self.repository.list_payment_receipts_by_appointment, appointment_id)

    async def get_appointment_receipt_pdf(self, appointment_id: int, receipt_id: int) -> tuple[bytes, str]:
        appointment = await asyncio.to_thread(self.repository.get_by_id, appointment_id)
        if appointment is None:
            raise ValueError("Cita no encontrada")

        def _fetch() -> Optional[dict[str, object]]:
            return self.repository.get_payment_receipt_file(appointment_id, receipt_id)

        row = await asyncio.to_thread(_fetch)
        if row is None:
            raise ValueError("Recibo no encontrado")
        raw_pdf = row.get("pdf")
        if raw_pdf is None:
            raise ValueError("Recibo sin archivo")
        fn = str(row.get("file_name") or "recibo.pdf")
        return bytes(raw_pdf), fn

    async def resend_appointment_payment_receipt(self, appointment_id: int, receipt_id: int) -> None:
        """Reenvía el PDF guardado al webhook de recibos (n8n / WhatsApp)."""

        def _build_payload() -> dict[str, object]:
            row = self.repository.get_payment_receipt_for_resend(appointment_id, receipt_id)
            if row is None:
                raise ValueError("Recibo no encontrado")
            raw_pdf = row.get("pdf")
            if raw_pdf is None:
                raise ValueError("Recibo sin archivo PDF")
            pdf_bytes = bytes(raw_pdf)
            get_row = getattr(self.repository, "get_row_for_payment_receipt", None)
            if callable(get_row):
                appt = get_row(appointment_id)
            else:
                appt = self.repository.get_by_id(appointment_id)
            if appt is None:
                raise ValueError("Cita no encontrada")
            fields = self._resolve_receipt_client_fields(appt)
            kind = str(row.get("kind") or "abono").strip() or "abono"
            try:
                amount = float(row.get("amount") or 0)
            except (TypeError, ValueError):
                amount = 0.0
            if amount <= 0:
                raise ValueError("El recibo no tiene un importe válido para reenviar")
            raw_pay = row.get("appointment_payment_id")
            pay_id: Optional[int] = None
            if raw_pay is not None:
                try:
                    pay_id = int(raw_pay)
                except (TypeError, ValueError):
                    pay_id = None
            raw_cust = row.get("customer_id")
            if raw_cust is None:
                raw_cust = getattr(appt, "customer_id", None)
            customer_id = int(raw_cust) if raw_cust is not None else None
            fname = str(row.get("file_name") or f"recibo_{appointment_id}_{receipt_id}.pdf")
            return self._payment_receipt_pdf_webhook_payload(
                appointment_id=int(appointment_id),
                receipt_id=int(receipt_id),
                customer_id=customer_id,
                customer_name=fields["client_name"],
                phone=fields["client_phone"],
                kind=kind,
                appointment_payment_id=pay_id if pay_id and pay_id > 0 else None,
                amount=amount,
                payment_note=str(row.get("note") or ""),
                file_name=fname,
                pdf_bytes=pdf_bytes,
            )

        payload = await asyncio.to_thread(_build_payload)
        await self._async_notify("payment_receipt_pdf", payload)

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

    def _ensure_active_store_id(self, store_id: int) -> int:
        sid = int(store_id)
        if sid <= 0:
            raise ValueError("STORE_NOT_ACTIVE")
        if self.store_repo is None:
            raise ValueError("STORE_NOT_ACTIVE")
        row = self.store_repo.get_by_id(sid)
        if row is None or not bool(row.get("is_active")):
            raise ValueError("STORE_NOT_ACTIVE")
        return sid

    async def list_stores(self, *, include_inactive: bool = False) -> list[StorePublic]:
        if self.store_repo is None:
            return []

        def _run() -> list[StorePublic]:
            rows = self.store_repo.list_stores(include_inactive=include_inactive)
            return [StorePublic.model_validate(r) for r in rows]

        return await asyncio.to_thread(_run)

    async def get_store(self, store_id: int) -> Optional[StorePublic]:
        if self.store_repo is None:
            return None

        def _run() -> Optional[StorePublic]:
            row = self.store_repo.get_by_id(store_id)
            return StorePublic.model_validate(row) if row else None

        return await asyncio.to_thread(_run)

    async def create_store(self, data: StoreCreate) -> int:
        if self.store_repo is None:
            raise RuntimeError("Repositorio de tiendas no configurado.")

        def _run() -> int:
            return self.store_repo.insert(
                name=data.name,
                address=data.address,
                phone=data.phone,
                email=data.email,
                is_active=data.is_active,
            )

        return await asyncio.to_thread(_run)

    async def update_store(self, store_id: int, data: StoreUpdate) -> None:
        if self.store_repo is None:
            raise RuntimeError("Repositorio de tiendas no configurado.")

        def _run() -> None:
            self.store_repo.update(
                store_id,
                name=data.name,
                address=data.address,
                phone=data.phone,
                email=data.email,
                is_active=data.is_active,
            )

        await asyncio.to_thread(_run)

    async def soft_delete_store(self, store_id: int) -> None:
        if self.store_repo is None:
            raise RuntimeError("Repositorio de tiendas no configurado.")

        def _run() -> None:
            row = self.store_repo.get_by_id(store_id)
            if row is None:
                raise ValueError("STORE_NOT_FOUND")
            if self.store_repo.count_users_with_store_id(int(store_id)) > 0:
                raise ValueError("STORE_IN_USE")
            self.store_repo.soft_delete(store_id)

        await asyncio.to_thread(_run)

    async def register_panel_user(self, data: PanelUserRegister) -> int:
        if self.panel_user_repo is None:
            raise RuntimeError("Repositorio de usuarios del panel no configurado.")

        def _run() -> int:
            store_id = self._ensure_active_store_id(data.store_id)
            with self.panel_user_repo.db.transaction() as conn:
                if self.panel_user_repo.get_by_username(data.username, conn):
                    raise ValueError("USERNAME_TAKEN")
                ph = hash_password(data.password)
                return self.panel_user_repo.insert(
                    username=data.username,
                    password_hash=ph,
                    first_name=data.first_name,
                    last_name=data.last_name,
                    address=data.address,
                    phone=data.phone,
                    store_id=store_id,
                    role=data.role,
                    is_active=True,
                    conn=conn,
                )

        return await asyncio.to_thread(_run)

    async def create_panel_user(self, data: PanelUserCreate) -> int:
        if self.panel_user_repo is None:
            raise RuntimeError("Repositorio de usuarios del panel no configurado.")

        def _run() -> int:
            store_id = self._ensure_active_store_id(data.store_id)
            with self.panel_user_repo.db.transaction() as conn:
                if self.panel_user_repo.get_by_username(data.username, conn):
                    raise ValueError("USERNAME_TAKEN")
                ph = hash_password(data.password)
                return self.panel_user_repo.insert(
                    username=data.username,
                    password_hash=ph,
                    first_name=data.first_name,
                    last_name=data.last_name,
                    address=data.address,
                    phone=data.phone,
                    store_id=store_id,
                    role=data.role,
                    is_active=data.is_active,
                    conn=conn,
                )

        return await asyncio.to_thread(_run)

    async def list_panel_users(self) -> list[PanelUserPublic]:
        if self.panel_user_repo is None:
            return []

        def _run() -> list[PanelUserPublic]:
            rows = self.panel_user_repo.list_public_rows()
            return [PanelUserPublic.model_validate(r) for r in rows]

        return await asyncio.to_thread(_run)

    async def list_panel_users_assignable_for_appointments(self) -> list[PanelUserAssignable]:
        if self.panel_user_repo is None:
            return []

        def _run() -> list[PanelUserAssignable]:
            rows = self.panel_user_repo.list_assignable_for_appointments()
            return [PanelUserAssignable.model_validate(r) for r in rows]

        return await asyncio.to_thread(_run)

    async def get_panel_user(self, user_id: int) -> Optional[PanelUserPublic]:
        if self.panel_user_repo is None:
            return None

        def _run() -> Optional[PanelUserPublic]:
            row = self.panel_user_repo.get_by_id(user_id)
            if row is None:
                return None
            out = {k: v for k, v in row.items() if k != "password_hash"}
            return PanelUserPublic.model_validate(out)

        return await asyncio.to_thread(_run)

    async def update_panel_user(self, user_id: int, data: PanelUserUpdate) -> None:
        if self.panel_user_repo is None:
            raise RuntimeError("Repositorio de usuarios del panel no configurado.")
        payload = data.model_dump(exclude_unset=True)
        if not payload:
            raise ValueError("EMPTY_UPDATE")
        if "password" in payload:
            payload["password_hash"] = hash_password(payload.pop("password"))

        def _run() -> None:
            upd = dict(payload)
            if "store_id" in upd:
                upd["store_id"] = self._ensure_active_store_id(int(upd["store_id"]))
            with self.panel_user_repo.db.transaction() as conn:
                if self.panel_user_repo.get_by_id(user_id, conn) is None:
                    raise ValueError("NOT_FOUND")
                self.panel_user_repo.update(user_id, upd, conn)
                if payload.get("role") == "administrador":
                    self.panel_user_repo.replace_module_keys(user_id, [], conn)

        try:
            await asyncio.to_thread(_run)
        except ValueError as e:
            if str(e) == "NOT_FOUND":
                raise ValueError("USER_NOT_FOUND") from e
            raise

    async def login_panel_user_session(self, username: str, password: str) -> Optional[PanelUserSessionPublic]:
        if self.panel_user_repo is None:
            return None

        def _run() -> Optional[PanelUserSessionPublic]:
            row = self.panel_user_repo.get_by_username(username)
            if not row or not row.get("is_active"):
                return None
            if not verify_password(password, str(row["password_hash"])):
                return None
            return PanelUserSessionPublic(
                id=int(row["id"]),
                username=str(row["username"]),
                role=str(row["role"]),
            )

        return await asyncio.to_thread(_run)

    async def get_panel_user_module_grants_raw(self, user_id: int) -> list[str]:
        if self.panel_user_repo is None:
            raise RuntimeError("Repositorio de usuarios del panel no configurado.")

        def _run() -> list[str]:
            row = self.panel_user_repo.get_by_id(user_id)
            if row is None:
                raise ValueError("USER_NOT_FOUND")
            if str(row.get("role")) == "administrador":
                return []
            return self.panel_user_repo.list_module_keys_for_user(user_id)

        try:
            return await asyncio.to_thread(_run)
        except ValueError as e:
            if str(e) == "USER_NOT_FOUND":
                raise ValueError("USER_NOT_FOUND") from e
            raise

    async def get_effective_panel_module_keys(self, user_id: int) -> list[str]:
        if self.panel_user_repo is None:
            raise RuntimeError("Repositorio de usuarios del panel no configurado.")

        def _run() -> list[str]:
            row = self.panel_user_repo.get_by_id(user_id)
            if row is None:
                raise ValueError("USER_NOT_FOUND")
            if str(row.get("role")) == "administrador":
                return sorted(ASSIGNABLE_PANEL_MODULE_KEYS)
            return self.panel_user_repo.list_module_keys_for_user(user_id)

        try:
            return await asyncio.to_thread(_run)
        except ValueError as e:
            if str(e) == "USER_NOT_FOUND":
                raise ValueError("USER_NOT_FOUND") from e
            raise

    async def set_panel_user_modules(self, user_id: int, data: PanelUserModulesBody) -> None:
        if self.panel_user_repo is None:
            raise RuntimeError("Repositorio de usuarios del panel no configurado.")

        def _run() -> None:
            with self.panel_user_repo.db.transaction() as conn:
                row = self.panel_user_repo.get_by_id(user_id, conn)
                if row is None:
                    raise ValueError("USER_NOT_FOUND")
                if str(row.get("role")) == "administrador":
                    raise ValueError("ADMIN_MODULES_FIXED")
                self.panel_user_repo.replace_module_keys(user_id, data.modules, conn)

        try:
            await asyncio.to_thread(_run)
        except ValueError as e:
            if str(e) == "USER_NOT_FOUND":
                raise ValueError("USER_NOT_FOUND") from e
            raise

    async def verify_panel_user_login(self, username: str, password: str) -> bool:
        if self.panel_user_repo is None:
            return False

        def _run() -> bool:
            row = self.panel_user_repo.get_by_username(username)
            if not row or not row.get("is_active"):
                return False
            return verify_password(password, str(row["password_hash"]))

        return await asyncio.to_thread(_run)

    async def _async_notify(self, event: str, payload: dict[str, object]) -> None:
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.notifier.notify, event, payload)
        except Exception as e:
            logger.warning("notify n8n failed: %s", e)
