"""Bloques reutilizables del formulario «Agendar cita» (mismo `session_state` que el diálogo).

Usa `render_agendar_booking_form_body` desde:
- `@st.dialog` en `citas_agendar_dialog`
- otros flujos que compartan las claves `ap_*` (p. ej. asistentes con pasos).
"""

from __future__ import annotations

from datetime import date
from typing import Optional

import streamlit as st

from streamlit_app.appointment_agenda_slots import (
    MAX_BOOKING_DURATION_SLOTS,
    MIN_BOOKING_DURATION_SLOTS,
)
from streamlit_app.appointment_slots import (
    available_start_slots,
    busy_slot_indices_for_day,
    time_slot_options,
)
from streamlit_app.citas_agendar_helpers import booking_duration_slots_from_session
from streamlit_app.citas_booking_meta import (
    BOOKING_WORK_KIND_META,
    BOOKING_WORK_KIND_ORDER,
    work_kind_to_assignee_role,
    work_kind_to_schedule_kind,
)
from streamlit_app.citas_panel_staff import ensure_assignable_staff
from streamlit_app.citas_schedule_queries import (
    appointments_for_artist_schedule,
    appointments_same_day_schedule_kind,
)
from streamlit_app.customer_sync import fetch_customer_by_document


def sync_pending_booking_document_type() -> None:
    """Evita escritura en widget `ap_doc_type` ya creado; consumir antes de crear widgets."""
    pending_doc_ty = st.session_state.pop("_ap_pending_doc_type_sync", None)
    if pending_doc_ty in ("CC", "TI", "CE", "PAS"):
        st.session_state["ap_doc_type"] = pending_doc_ty


def render_agendar_required_banner_html() -> None:
    st.markdown(
        '<div class="dlg-appt-req-banner">Campos obligatorios</div>',
        unsafe_allow_html=True,
    )


def render_agendar_work_kind_and_staff_pick() -> Optional[int]:
    """Dibuja tipo de trabajo y profesional; devuelve `assigned_id` ya resuelto o None si falta staffing."""
    c_wk, c_art = st.columns(2)
    with c_wk:
        st.markdown('<p class="dlg-appt-col-h">Tipo de trabajo</p>', unsafe_allow_html=True)
        st.selectbox(
            "¿Qué se va a realizar? *",
            options=list(BOOKING_WORK_KIND_ORDER),
            key="ap_work_kind",
            format_func=lambda k: str(BOOKING_WORK_KIND_META[k]["label"]),
            help="Define el servicio y qué profesional se listará (tatuador o perforador).",
        )

    wk_sel = str(st.session_state.get("ap_work_kind") or "piercing")
    if wk_sel not in BOOKING_WORK_KIND_META:
        wk_sel = "piercing"
    need_role = work_kind_to_assignee_role(wk_sel)

    assigned_id: Optional[int] = None
    with c_art:
        st.markdown('<p class="dlg-appt-col-h">Profesional asignado</p>', unsafe_allow_html=True)
        from streamlit_app.panel_auth import panel_auth_enabled

        role_me = str(st.session_state.get("_panel_user_role") or "")
        uid_me = st.session_state.get("_panel_user_id")
        locked_self = (
            panel_auth_enabled()
            and not st.session_state.get("_panel_session_full_access")
            and role_me == need_role
            and uid_me is not None
        )
        staff_opts = [s for s in ensure_assignable_staff() if str(s.get("role")) == need_role]
        if locked_self:
            assigned_id = int(uid_me)
            st.session_state["ap_assigned_staff_id"] = assigned_id
            st.caption(
                "Las franjas horarias se calculan con tu disponibilidad; la cita quedará asignada a **tu usuario** del panel."
            )
        elif not staff_opts:
            st.error(
                f"No hay ningún usuario activo con rol **{need_role}** en el panel. "
                "Da de alta al profesional en **Gestión de usuarios** antes de agendar."
            )
            return None
        else:
            labels_p = [
                f"{s.get('first_name', '')} {s.get('last_name', '')} (@{s.get('username', '')})"
                for s in staff_opts
            ]
            pick_key = "ap_assigned_staff_pick"
            if pick_key not in st.session_state or st.session_state[pick_key] not in labels_p:
                st.session_state[pick_key] = labels_p[0]
            choice_p = st.selectbox(
                "Artista / profesional *",
                options=labels_p,
                key=pick_key,
                help="Cada profesional tiene su propia ocupación por día; elige quién atenderá.",
            )
            idx_p = labels_p.index(choice_p)
            assigned_id = int(staff_opts[idx_p]["id"])
            st.session_state["ap_assigned_staff_id"] = assigned_id
    return assigned_id


def render_agendar_duration_and_start_slot(*, picked: date) -> None:
    c_dur, c_hr = st.columns(2)
    with c_dur:
        st.markdown('<p class="dlg-appt-col-h">Duración en agenda</p>', unsafe_allow_html=True)
        st.number_input(
            "Franjas de 30 min a reservar *",
            min_value=MIN_BOOKING_DURATION_SLOTS,
            max_value=MAX_BOOKING_DURATION_SLOTS,
            step=1,
            key="ap_duration_slots",
            help="Desde la hora de inicio se bloquean tantas franjas de media hora. No está ligada al tipo de trabajo.",
        )

    slot_opts = time_slot_options()
    wk = str(st.session_state.get("ap_work_kind") or "piercing")
    if wk not in BOOKING_WORK_KIND_META:
        wk = "piercing"
    need_slots = booking_duration_slots_from_session()
    sched_kind = work_kind_to_schedule_kind(wk)
    raw_appt_list = list(st.session_state.get("_ap_list") or [])
    aid_raw = st.session_state.get("ap_assigned_staff_id")
    artist_for_busy: Optional[int] = None
    if aid_raw not in (None, "", 0):
        try:
            artist_for_busy = int(aid_raw)
        except (TypeError, ValueError):
            artist_for_busy = None
    if artist_for_busy is not None:
        day_rows_cal = appointments_for_artist_schedule(raw_appt_list, picked, artist_for_busy, schedule_kind=sched_kind)
    else:
        day_rows_cal = appointments_same_day_schedule_kind(raw_appt_list, picked, sched_kind)
    busy_idx = busy_slot_indices_for_day(day_rows_cal, slot_opts)
    avail_slots = available_start_slots(slot_opts, need_slots, busy_idx)
    cur_slot = st.session_state.get("ap_slot")
    if avail_slots and cur_slot not in avail_slots:
        st.session_state["ap_slot"] = avail_slots[0]

    with c_hr:
        st.markdown('<p class="dlg-appt-col-h">Hora de inicio</p>', unsafe_allow_html=True)
        if not avail_slots:
            st.warning(
                "No quedan franjas libres ese día para esta duración. Prueba otro día o revisa las citas ya cargadas."
            )
        else:
            st.selectbox(
                "Franja de inicio *",
                options=avail_slots,
                key="ap_slot",
                help=f"Se reservan {need_slots} franja(s) de 30 min desde esta hora.",
            )
            slot_vis = str(st.session_state.get("ap_slot") or "").strip()
            st.caption(f"Inicio **{slot_vis or '—'}** hora local (duración **{need_slots * 30}** min).")


def render_agendar_picked_date_summary(*, picked: date) -> None:
    st.markdown(f"**Fecha de la cita:** {picked.strftime('%d/%m/%Y')} _(elegida en el calendario)_")


def render_agendar_document_verify_block() -> None:
    st.markdown('<p class="dlg-appt-col-h">Identificación del cliente</p>', unsafe_allow_html=True)
    c_doc_l, c_doc_r = st.columns(2)
    with c_doc_l:
        st.selectbox(
            "Tipo de identificación del cliente *",
            options=["CC", "TI", "CE", "PAS"],
            format_func=lambda x: {
                "CC": "CC — Cédula",
                "TI": "TI — Tarjeta de identidad",
                "CE": "CE — Extranjería",
                "PAS": "PAS — Pasaporte",
            }[x],
            key="ap_doc_type",
        )
        st.text_input(
            "Número de identificación del cliente *",
            key="ap_doc_number",
            placeholder="Sin puntos ni espacios, si es posible",
        )
    with c_doc_r:
        st.markdown("<div style='height:4.5rem'></div>", unsafe_allow_html=True)
        if st.button(
            "Verificar identificación",
            type="secondary",
            use_container_width=True,
            key="ap_btn_verify_doc",
        ):
            doc_in = (st.session_state.get("ap_doc_number") or "").strip()
            if len(doc_in) < 5:
                st.session_state["_ap_verify_level"] = "error"
                st.session_state["_ap_verify_msg"] = (
                    "Ingresa un número de identificación válido (mínimo 5 caracteres)."
                )
                st.session_state["_ap_doc_verified"] = False
            else:
                ok_f, msg_f, row_f = fetch_customer_by_document(doc_in)
                if not ok_f:
                    st.session_state["_ap_verify_level"] = "error"
                    st.session_state["_ap_verify_msg"] = msg_f
                    st.session_state["_ap_doc_verified"] = False
                elif msg_f == "not_found":
                    st.session_state["_ap_booking_customer_id"] = None
                    st.session_state["_ap_need_new_customer"] = True
                    st.session_state["_ap_doc_verified"] = True
                    st.session_state["_ap_verified_doc_number"] = doc_in
                    st.session_state["_ap_verify_level"] = "warning"
                    st.session_state["_ap_verify_msg"] = (
                        "Cliente no registrado. Completa nombre, apellido, celular y correo. "
                        "La fecha de nacimiento y el tutor (si aplica) se registran al firmar el contrato o en la ficha del cliente."
                    )
                else:
                    st.session_state["_ap_booking_customer_id"] = int(row_f["id"])
                    st.session_state["_ap_need_new_customer"] = False
                    st.session_state["_ap_doc_verified"] = True
                    st.session_state["_ap_verified_doc_number"] = doc_in
                    st.session_state["_ap_booking_customer_snapshot"] = dict(row_f)
                    st.session_state["ap_fn"] = str(row_f.get("first_name") or "")
                    st.session_state["ap_ln"] = str(row_f.get("last_name") or "")
                    st.session_state["ap_phone"] = str(row_f.get("phone_number") or "")
                    st.session_state["ap_email"] = str(row_f.get("email") or "")
                    raw_dt = str(row_f.get("document_type") or "").strip().upper()
                    if raw_dt in ("CC", "TI", "CE", "PAS"):
                        st.session_state["_ap_pending_doc_type_sync"] = raw_dt
                    st.session_state["_ap_verify_level"] = "success"
                    st.session_state["_ap_verify_msg"] = f"Cliente encontrado (id {row_f['id']}). Datos cargados."
            st.rerun()


def render_agendar_verify_feedback_banner() -> None:
    v_lvl = st.session_state.get("_ap_verify_level")
    v_msg = st.session_state.get("_ap_verify_msg")
    if v_msg and v_lvl:
        if v_lvl == "error":
            st.error(v_msg)
        elif v_lvl == "success":
            st.success(v_msg)
        else:
            st.warning(v_msg)


def render_agendar_minor_doc_caption_if_new_customer() -> None:
    if st.session_state.get("_ap_need_new_customer"):
        st.caption(
            "**Tarjeta de identidad (TI)** u otros documentos: se admite al agendar. "
            "La fecha de nacimiento y el estado de menor/tutor se definen al completar la ficha o en la firma del contrato."
        )


def render_agendar_customer_name_contact_fields() -> None:
    st.markdown('<p class="dlg-appt-col-h">Cliente</p>', unsafe_allow_html=True)
    cl1, cl2 = st.columns(2)
    with cl1:
        st.text_input("Nombre *", key="ap_fn")
        st.text_input(
            "Celular *",
            key="ap_phone",
            help="10 dígitos; puedes incluir espacios o prefijo, se cuentan solo los números.",
        )
    with cl2:
        st.text_input("Apellido *", key="ap_ln")
        st.text_input("Correo electrónico *", key="ap_email")


def render_agendar_design_notes_priority_and_amounts() -> None:
    from app.domain.appointment_money import MIN_APPOINTMENT_TOTAL_COP, format_cop as _format_cop

    st.markdown('<p class="dlg-appt-col-h">Cita y montos</p>', unsafe_allow_html=True)
    cm1, cm2 = st.columns(2)
    with cm1:
        st.text_area(
            "Descripción del diseño (opcional)",
            height=68,
            key="ap_design",
            help="Se guarda en el detalle de la cita junto con las observaciones.",
        )
        st.text_area(
            "Notas u observaciones (opcional)",
            height=68,
            key="ap_det",
            help="Texto adicional (indicaciones, zona, etc.).",
        )
        st.checkbox(
            "Cita prioritaria",
            key="ap_priority",
            help="Se muestra con etiqueta roja en calendario y listado (prevalece sobre cliente nuevo/recurrente salvo reprogramación).",
        )
    with cm2:
        total_amount = st.number_input(
            "Valor total del trabajo (COP) *",
            min_value=float(MIN_APPOINTMENT_TOTAL_COP),
            step=5000.0,
            format="%.0f",
            key="ap_total",
        )
        deposit = st.number_input(
            "Saldo abonado (COP) *",
            min_value=float(MIN_APPOINTMENT_TOTAL_COP),
            step=5000.0,
            format="%.0f",
            key="ap_dep",
            help=f"Mínimo {_format_cop(MIN_APPOINTMENT_TOTAL_COP)}.",
        )
        pending_balance = round(float(total_amount) - float(deposit), 2)
        st.caption(f"Saldo pendiente calculado: {_format_cop(max(pending_balance, 0))}")


def render_agendar_booking_form_body(*, picked: date) -> None:
    """Cuerpo completo del formulario (widgets). Asume día ya validado."""
    st.markdown('<div class="dlg-appt-root" aria-hidden="true"></div>', unsafe_allow_html=True)
    sync_pending_booking_document_type()
    render_agendar_required_banner_html()
    render_agendar_work_kind_and_staff_pick()
    render_agendar_duration_and_start_slot(picked=picked)
    render_agendar_picked_date_summary(picked=picked)
    render_agendar_document_verify_block()
    render_agendar_verify_feedback_banner()
    render_agendar_minor_doc_caption_if_new_customer()
    render_agendar_customer_name_contact_fields()
    render_agendar_design_notes_priority_and_amounts()


__all__ = [
    "render_agendar_booking_form_body",
    "render_agendar_customer_name_contact_fields",
    "render_agendar_design_notes_priority_and_amounts",
    "render_agendar_document_verify_block",
    "render_agendar_duration_and_start_slot",
    "render_agendar_minor_doc_caption_if_new_customer",
    "render_agendar_required_banner_html",
    "render_agendar_verify_feedback_banner",
    "render_agendar_work_kind_and_staff_pick",
    "sync_pending_booking_document_type",
]
