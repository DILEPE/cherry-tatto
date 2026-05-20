"""POST de nueva cita desde el estado estándar `ap_*` (compartido con el diálogo y otros flujos)."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict

import streamlit as st
from pydantic import ValidationError

from app.domain.appointment_money import MIN_APPOINTMENT_TOTAL_COP, format_cop
from app.schemas.customer import CUSTOMER_BIRTH_PENDING, CustomerCreate
from streamlit_app import api_client
from streamlit_app.appointment_agenda_slots import append_agenda_slots_marker
from streamlit_app.appointment_dates import combine_appointment_datetime
from streamlit_app.appointment_slots import (
    available_start_slots,
    busy_slot_indices_for_day,
    time_slot_options,
)
from streamlit_app.citas_agendar_customer import booking_customer_create_for_existing_client
from streamlit_app.citas_agendar_helpers import (
    booking_duration_slots_from_session,
    booking_observations_and_design_for_api,
    initial_receipt_success_message,
    show_validation_errors,
)
from streamlit_app.citas_agendar_state import (
    queue_appointment_action_success,
    reset_appointment_form_state,
)
from streamlit_app.citas_booking_meta import BOOKING_WORK_KIND_META, service_and_detail_for_work_kind, work_kind_to_schedule_kind
from streamlit_app.citas_schedule_queries import appointments_for_artist_schedule
from streamlit_app.http_error_detail import format_http_error_detail
from streamlit_app.validation import validate_appointment


def render_agendar_create_cancel_footer(*, picked: date, today_d: date) -> None:
    """Botones Crear / Cancelar (misma lógica que el diálogo)."""
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Crear cita", type="primary", use_container_width=True, key="btn_appt_create"):
            handle_agendar_booking_submit(picked=picked, today_d=today_d)
    with c2:
        if st.button("Cancelar", use_container_width=True, key="btn_appt_cancel"):
            reset_appointment_form_state()
            st.session_state.pop("_ap_dlg", None)
            st.rerun()


def handle_agendar_booking_submit(*, picked: date, today_d: date) -> None:
    if not st.session_state.get("_ap_doc_verified"):
        st.error("Debes verificar el documento antes de crear la cita.")
        return
    doc_in = (st.session_state.get("ap_doc_number") or "").strip()
    if len(doc_in) < 5:
        st.error("El número de documento no es válido.")
        return
    snap = (st.session_state.get("_ap_verified_doc_number") or "").strip()
    if snap and snap != doc_in:
        st.error("El documento cambió respecto al verificado. Pulsa de nuevo «Verificar documento».")
        return
    cust_id = st.session_state.get("_ap_booking_customer_id")
    need_new = bool(st.session_state.get("_ap_need_new_customer"))
    aid_submit = st.session_state.get("ap_assigned_staff_id")
    if aid_submit is None or aid_submit == "":
        st.error("Indica el **profesional** que atenderá la cita (tatuador o perforador).")
        return
    aid_int = int(aid_submit)
    wk_submit = str(st.session_state.get("ap_work_kind") or "piercing")
    if wk_submit not in BOOKING_WORK_KIND_META:
        wk_submit = "piercing"
    need_slots_submit = booking_duration_slots_from_session()
    sched_submit = work_kind_to_schedule_kind(wk_submit)
    slot_opts_chk = time_slot_options()
    raw_chk = list(st.session_state.get("_ap_list") or [])
    day_chk = appointments_for_artist_schedule(raw_chk, picked, aid_int, schedule_kind=sched_submit)
    busy_chk = busy_slot_indices_for_day(day_chk, slot_opts_chk)
    avail_chk = available_start_slots(slot_opts_chk, need_slots_submit, busy_chk)
    if not avail_chk:
        st.error("No hay franja disponible ese día para la duración de este trabajo.")
        return
    slot_str = (st.session_state.get("ap_slot") or "").strip()
    if slot_str not in avail_chk:
        st.error("La franja elegida ya no está libre. Vuelve a seleccionar la hora.")
        return

    detail_raw = booking_observations_and_design_for_api()
    fn = str(st.session_state.get("ap_fn") or "").strip()
    ln = str(st.session_state.get("ap_ln") or "").strip()
    phone = str(st.session_state.get("ap_phone") or "").strip()

    total_amount = float(int(round(float(st.session_state.get("ap_total") or 0))))
    deposit = float(int(round(float(st.session_state.get("ap_dep") or 0))))
    service, detail_for_api = service_and_detail_for_work_kind(wk_submit, detail_raw)
    detail_for_api = append_agenda_slots_marker(detail_for_api, need_slots_submit)
    full_name = f"{fn} {ln}".strip()
    dt_str = combine_appointment_datetime(picked, slot_str)
    email_s = (st.session_state.get("ap_email") or "").strip()

    valid, errs = validate_appointment(
        full_name,
        phone,
        email_s,
        service,
        dt_str,
        detail_raw,
        deposit,
    )
    if not valid:
        show_validation_errors(errs)
        return
    if deposit > total_amount:
        st.error("El saldo abonado no puede ser mayor que el valor total del trabajo.")
        return
    if deposit < float(MIN_APPOINTMENT_TOTAL_COP):
        st.error(f"El saldo abonado debe ser al menos {format_cop(MIN_APPOINTMENT_TOTAL_COP)}.")
        return
    if picked < today_d:
        st.error("La fecha de la cita no puede ser anterior a hoy.")
        return

    dep_norm = max(0.0, float(int(round(float(deposit)))))
    total_int = float(int(round(float(total_amount))))
    if total_int < float(MIN_APPOINTMENT_TOTAL_COP):
        st.error(f"El valor total del trabajo debe ser al menos {format_cop(MIN_APPOINTMENT_TOTAL_COP)}.")
        return

    appt_payload: Dict[str, Any] = {
        "name": full_name,
        "phone": phone,
        "service": (service or "").strip(),
        "date": dt_str,
        "detail": detail_for_api,
        "deposit": dep_norm,
        "total_amount": total_int,
        "pending_balance": float(max(round(total_int - dep_norm, 2), 0)),
        "is_priority": bool(st.session_state.get("ap_priority")),
        "assigned_panel_user_id": aid_int,
    }

    if cust_id is not None:
        appt_payload["customer_id"] = int(cust_id)
        snap_dict = st.session_state.get("_ap_booking_customer_snapshot")
        if not isinstance(snap_dict, dict) or int(snap_dict.get("id") or 0) != int(cust_id):
            st.error(
                "Los datos del cliente no coinciden con la verificación. Pulsa **Verificar documento** de nuevo."
            )
            return
        try:
            c_exist = booking_customer_create_for_existing_client(
                snap_dict,
                first_name=fn,
                last_name=ln,
                phone_number=phone,
                email_s=email_s,
                document_number=doc_in,
            )
        except ValidationError as ve:
            st.error(str(ve))
            return
        appt_payload["customer"] = c_exist.model_dump(mode="json")
    elif need_new:
        doc_ty = str(st.session_state.get("ap_doc_type") or "CC")
        if doc_ty not in ("CC", "TI", "CE", "PAS"):
            doc_ty = "CC"
        try:
            c_new = CustomerCreate(
                first_name=fn,
                last_name=ln,
                birth_date=CUSTOMER_BIRTH_PENDING,
                document_type=doc_ty,  # type: ignore[arg-type]
                document_number=doc_in,
                document_issue_date=None,
                email=email_s,
                phone_number=phone,
                address=None,
                is_minor=False,
                guardian_name=None,
                guardian_document_type=None,
                guardian_document_number=None,
                guardian_document_issue_date=None,
            )
        except ValidationError as ve:
            st.error(str(ve))
            return
        appt_payload["customer"] = c_new.model_dump(mode="json")
    else:
        st.error("Verifica el documento antes de crear la cita.")
        return

    with st.spinner("Guardando cita…"):
        ok_a, code_a, data_a = api_client.post_appointment(appt_payload)
    if ok_a:
        st.session_state["_ap_reload"] = True
        dep_created = max(0.0, round(float(appt_payload.get("deposit") or 0), 2))
        ok_msg = initial_receipt_success_message(dep_created, str(appt_payload.get("service") or ""))
        queue_appointment_action_success(ok_msg)
        reset_appointment_form_state()
        st.session_state.pop("_ap_dlg", None)
        st.rerun()
    else:
        st.toast(
            f"Error HTTP {code_a}: {format_http_error_detail(data_a)}",
            icon="❌",
            duration="long",
        )


__all__ = [
    "handle_agendar_booking_submit",
    "render_agendar_create_cancel_footer",
]
