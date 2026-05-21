"""Dialogs cita desde fila: repr., montos, anular, recibos."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

import streamlit as st

from app.domain.appointment_money import coerce_float, format_cop
from app.domain.contract_kinds import appointment_to_contract_kind
from streamlit_app import api_client
from streamlit_app.appointment_agenda_slots import duration_slots_for_existing_appointment
from streamlit_app.appointment_dates import combine_appointment_datetime, format_api_datetime_compact_es
from streamlit_app.appointment_slots import (
    available_start_slots,
    busy_slot_indices_for_day,
    parse_existing_appointment_slot,
    time_slot_options,
)
from streamlit_app.appointment_staff_labels import assigned_artist_display_name
from streamlit_app.citas_agendar_dialog import queue_appointment_action_success
from streamlit_app.citas_row_policy import reprogram_disabled_for_row
from streamlit_app.citas_schedule_queries import (
    appointments_for_artist_schedule,
    appointments_same_day_schedule_kind,
)
from streamlit_app.http_error_detail import format_http_error_detail
from streamlit_app.state.appointment_cache import (
    get_appointment_payments_cached,
    purge_appointment_receipt_caches,
)
from streamlit_app.state.appointment_keys import (
    KEY_FIN_PAYMENTS_PFX,
    KEY_RECEIPT_PDF_PFX,
    KEY_RECEIPTS_LIST_PFX,
    KEY_TOAST_FIN_SAVE_ERR,
)


def toast_financial_save_error_if_any() -> None:
    save_err = st.session_state.get("_ap_fin_save_error")
    if not save_err:
        st.session_state.pop(KEY_TOAST_FIN_SAVE_ERR, None)
        return
    if st.session_state.get(KEY_TOAST_FIN_SAVE_ERR) != save_err:
        st.session_state[KEY_TOAST_FIN_SAVE_ERR] = save_err
        st.toast(str(save_err), icon="❌", duration="long")

def _shift_years(base: date, years: int) -> date:
    target_year = base.year + years
    try:
        return base.replace(year=target_year)
    except ValueError:
        return base.replace(year=target_year, day=28)


def _date_range_100y_window() -> tuple[date, date]:
    today = date.today()
    return _shift_years(today, -100), _shift_years(today, 100)

def cleanup_reprogram_dialog_state() -> None:
    keys = ("_ap_reprogram_seed_appt_id", "ap_reprogram_date", "ap_reprogram_slot", "ap_reprogram_detail")
    for k in keys:
        st.session_state.pop(k, None)

@st.dialog("Reprogramar cita", width="medium", dismissible=False)
def dialog_reprogramar_cita() -> None:
    appt = st.session_state.get("_ap_reprogram_item") or {}
    appt_id = int(appt.get("id", 0) or 0)
    if appt_id <= 0:
        st.error("No se encontró la cita a reprogramar.")
        if st.button("Cerrar", use_container_width=True):
            st.session_state.pop("_ap_reprogram_item", None)
            cleanup_reprogram_dialog_state()
            st.rerun()
        return
    if reprogram_disabled_for_row(appt):
        st.warning(
            "No se puede reprogramar esta cita: debe estar **Agendada** o **Reprogramada**, "
            "sin **contrato firmado** y no cancelada."
        )
        if st.button("Cerrar", use_container_width=True, key="ap_reprogram_blocked_close"):
            st.session_state.pop("_ap_reprogram_item", None)
            cleanup_reprogram_dialog_state()
            st.rerun()
        return
    seed_key = "_ap_reprogram_seed_appt_id"
    detail_default = str(appt.get("detail") or "")
    _, max_date_appt = _date_range_100y_window()
    # Una sola fuente de verdad: session_state por key — evita value+key (provoca glitch del popover Calendar)
    if st.session_state.get(seed_key) != appt_id:
        st.session_state[seed_key] = appt_id
        d0, sl0 = parse_existing_appointment_slot(appt.get("appointment_date", appt.get("date")))
        today_d = date.today()
        st.session_state["ap_reprogram_date"] = d0 if d0 >= today_d else today_d
        st.session_state["ap_reprogram_slot"] = sl0
        st.session_state["ap_reprogram_detail"] = detail_default

    st.caption(
        f"Cita #{appt_id} · {appt.get('customer_name', appt.get('name', ''))} · "
        f"Artista: **{assigned_artist_display_name(appt)}**"
    )
    # Detalle primero para no autofocos en el calendar al abrir el diálogo
    new_detail = st.text_area(
        "Detalle actualizado (opcional)",
        height=90,
        key="ap_reprogram_detail",
    )
    today_d = date.today()
    new_date = st.date_input(
        "Nueva fecha de cita",
        min_value=today_d,
        max_value=max_date_appt,
        key="ap_reprogram_date",
        format="DD/MM/YYYY",
    )
    slot_opts = time_slot_options()
    need_slots_repr = duration_slots_for_existing_appointment(appt)
    raw_list_repr = list(st.session_state.get("_ap_list") or [])
    sched_repr = appointment_to_contract_kind(appt)
    ra_raw = appt.get("assigned_panel_user_id")
    artist_repr: Optional[int] = None
    if ra_raw not in (None, "", 0):
        try:
            artist_repr = int(ra_raw)
        except (TypeError, ValueError):
            artist_repr = None
    if artist_repr is not None:
        day_rows_repr = appointments_for_artist_schedule(
            raw_list_repr,
            new_date,
            artist_repr,
            schedule_kind=sched_repr,
            exclude_appointment_id=appt_id,
        )
        st.caption(
            "Franjas según **este profesional** y solo citas del **mismo tipo** (tatuaje o piercing)."
        )
    else:
        day_rows_repr = appointments_same_day_schedule_kind(
            raw_list_repr, new_date, sched_repr
        )
        st.caption(
            "Sin profesional asignado en base de datos; se usan citas del **mismo tipo** ese día."
        )
    busy_repr = busy_slot_indices_for_day(day_rows_repr, slot_opts)
    avail_repr = available_start_slots(slot_opts, need_slots_repr, busy_repr)
    if not avail_repr:
        st.warning(
            "No hay franjas libres ese día para esta duración. Puedes forzar una hora de la lista completa abajo; revisa conflictos en agenda."
        )
        avail_repr = slot_opts
    cur_sl = st.session_state.get("ap_reprogram_slot")
    if cur_sl not in avail_repr:
        st.session_state["ap_reprogram_slot"] = avail_repr[0]
    new_slot = st.selectbox(
        "Nueva franja horaria *",
        options=avail_repr,
        key="ap_reprogram_slot",
    )
    dt_reschedule = combine_appointment_datetime(new_date, str(new_slot))
    c1, c2 = st.columns(2)
    with c1:
        if st.button(
            "Guardar reprogramación",
            type="primary",
            use_container_width=True,
            key="ap_reprogram_save_btn",
        ):
            with st.spinner("Aplicando reprogramación…"):
                ok, code, data = api_client.patch_appointment_reschedule(
                    appt_id,
                    dt_reschedule,
                    (new_detail or "").strip() or None,
                )
            if ok:
                pretty = format_api_datetime_compact_es(dt_reschedule)
                queue_appointment_action_success(
                    f"**Cita reprogramada** · #{appt_id} · nueva fecha y hora: **{pretty}**."
                )
                st.session_state["_ap_reload"] = True
                st.session_state.pop("_ap_reprogram_item", None)
                cleanup_reprogram_dialog_state()
                st.rerun()
            else:
                st.toast(
                    f"Error HTTP {code}: {format_http_error_detail(data)}",
                    icon="❌",
                    duration="long",
                )
    with c2:
        if st.button("Cancelar", use_container_width=True, key="ap_reprogram_close_btn"):
            st.session_state.pop("_ap_reprogram_item", None)
            cleanup_reprogram_dialog_state()
            st.rerun()
def label_cancel_abono(v: str) -> str:
    if v == "credito_cliente":
        return "Saldo a favor del cliente — el abono pasa a crédito interno y deja de contar como cobrado sobre la cita"
    return "Devolución — el abono deja la cita como no cobrado (sin saldo a favor aquí)"

@st.dialog("Confirmar anulación", width="medium", dismissible=False)
def dialog_cancelar_cita() -> None:
    appt = st.session_state.get("_ap_cancel_item") or {}
    appt_id = int(appt.get("id", 0) or 0)
    if appt_id <= 0:
        st.error("No se encontró la cita a anular.")
        if st.button("Cerrar", use_container_width=True, key="ap_cancel_close_missing"):
            st.session_state.pop("_ap_cancel_item", None)
            st.rerun()
        return
    deposit = float(appt.get("deposit") or 0)
    art_nm = assigned_artist_display_name(appt)
    warning = (
        f"Vas a anular la cita #{appt_id} de "
        f"{appt.get('customer_name', appt.get('name', 'cliente'))}. "
        f"Artista asignado: **{art_nm}**. Esta acción cambia el estado a Cancelada."
    )
    if deposit > 0:
        warning += f" Hay {format_cop(deposit)} abonados en esta fila."
    else:
        warning += " No hay abonos registrados en esta cita."
    st.warning(warning)

    cancel_abono: str
    if deposit > 0:
        st.markdown("Si hubo abono, cómo debe reflejarse para **resumen y totales**:", unsafe_allow_html=True)
        cancel_abono = st.radio(
            "Tratamiento del abono",
            ("credito_cliente", "devolucion"),
            format_func=label_cancel_abono,
            horizontal=False,
            key=f"dlg_cancel_abono_radio_{appt_id}",
            label_visibility="visible",
        )
    else:
        cancel_abono = "devolucion"
        st.caption("Sin abono; la anulación solo cierra la cita en el sistema.")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Sí, anular", type="primary", use_container_width=True, key="ap_cancel_confirm_btn"):
            with st.spinner("Anulando cita…"):
                ok, code, data = api_client.patch_appointment_status(appt_id, "Cancelada", cancel_abono)
            if ok:
                queue_appointment_action_success(
                    f"**Cita anulada** · #{appt_id} · estado **Cancelada**."
                )
                st.session_state["_ap_reload"] = True
                st.session_state.pop("_ap_cancel_item", None)
                st.rerun()
            else:
                st.toast(
                    f"Error HTTP {code}: {format_http_error_detail(data)}",
                    icon="❌",
                    duration="long",
                )
    with c2:
        if st.button("No, volver", use_container_width=True, key="ap_cancel_back_btn"):
            st.session_state.pop("_ap_cancel_item", None)
            st.rerun()

@st.dialog("Ajustar montos", width="medium", dismissible=False)
def dialog_ajustar_montos() -> None:
    appt = st.session_state.get("_ap_fin_item") or {}
    appt_id = int(appt.get("id", 0) or 0)
    status = str(appt.get("status") or "Agendada")
    if appt_id <= 0:
        st.error("No se encontró la cita.")
        if st.button("Cerrar", use_container_width=True, key="ap_fin_close_missing"):
            st.session_state.pop("_ap_fin_item", None)
            st.rerun()
        return
    if status not in {"Agendada", "Reprogramada"}:
        st.error("Solo puedes editar montos en estados Agendada o Reprogramada.")
        if st.button("Cerrar", use_container_width=True, key="ap_fin_close_invalid"):
            st.session_state.pop("_ap_fin_item", None)
            st.rerun()
        return
    st.caption(
        f"Cita #{appt_id} · Estado: {status} · Artista: **{assigned_artist_display_name(appt)}**"
    )

    if st.session_state.get("_ap_fin_dialog_appt_id") != appt_id:
        st.session_state.pop("_ap_fin_save_error", None)
    st.session_state["_ap_fin_dialog_appt_id"] = appt_id

    st.markdown("##### Historial de abonos")
    ok_p, code_p, payments = get_appointment_payments_cached(appt_id)
    if ok_p and isinstance(payments, list):
        if payments:
            for p in payments:
                when = str(p.get("created_at") or "")
                note = str(p.get("note") or "Sin nota")
                amount = coerce_float(p.get("amount"), 0.0)
                st.write(f"- {when[:19]} · {format_cop(amount)} · {note}")
        else:
            st.info("Aún no hay abonos registrados.")
    else:
        st.warning(f"No se pudo cargar historial (HTTP {code_p}).")

    current_total = float(appt.get("total_amount") or 0)
    current_deposit = float(appt.get("deposit") or 0)
    total_amount = st.number_input(
        "Valor total del trabajo (COP)",
        min_value=0.0,
        step=10000.0,
        value=current_total,
        key="ap_fin_total",
    )
    pending = round(float(total_amount) - float(current_deposit), 2)
    st.caption(f"Abonado actual: {format_cop(current_deposit)}")
    st.caption(f"Saldo pendiente calculado: {format_cop(max(pending, 0))}")

    pend_ui = max(float(pending), 0.0)
    can_add_extra = pend_ui > 0.009
    if not can_add_extra:
        st.info("Trabajo cubierto: no hay saldo pendiente; no se pueden agregar abonos adicionales.")
        st.session_state["ap_fin_extra_payment"] = 0.0
        st.session_state["ap_fin_extra_note"] = ""

    extra_payment = st.number_input(
        "Agregar abono adicional (COP)",
        min_value=0.0,
        max_value=float(pend_ui) if can_add_extra else 0.0,
        step=10000.0,
        key="ap_fin_extra_payment",
        disabled=not can_add_extra,
        help=(
            "Solo si el saldo pendiente es mayor a cero."
            if can_add_extra
            else "Saldo pendiente en cero; no aplica otro abono."
        ),
    )
    payment_note = st.text_input(
        "Nota del abono (opcional)",
        key="ap_fin_extra_note",
        placeholder="Ej: abono en efectivo",
        disabled=not can_add_extra,
    )

    save_err = st.session_state.get("_ap_fin_save_error")
    toast_financial_save_error_if_any()

    c1, c2 = st.columns(2)
    with c1:
        do_save = st.button("Guardar", type="primary", use_container_width=True, key="ap_fin_save_btn")
    with c2:
        do_cancel = st.button("Cancelar", use_container_width=True, key="ap_fin_cancel_btn")

    if save_err:
        if st.button("Cerrar", use_container_width=True, key="ap_fin_err_close"):
            st.session_state.pop("_ap_fin_save_error", None)
            with st.spinner("Cerrando…"):
                st.session_state.pop("_ap_fin_item", None)
                st.session_state.pop("ap_fin_total", None)
                st.session_state.pop("ap_fin_extra_payment", None)
                st.session_state.pop("ap_fin_extra_note", None)
                st.session_state.pop("_ap_fin_dialog_appt_id", None)
            st.rerun()

    if do_cancel:
        st.session_state.pop("_ap_fin_save_error", None)
        with st.spinner("Cerrando…"):
            st.session_state.pop("_ap_fin_item", None)
            st.session_state.pop("ap_fin_total", None)
            st.session_state.pop("ap_fin_extra_payment", None)
            st.session_state.pop("ap_fin_extra_note", None)
            st.session_state.pop("_ap_fin_dialog_appt_id", None)
        st.rerun()

    if do_save:
        if current_deposit > total_amount:
            st.session_state["_ap_fin_save_error"] = (
                "El abonado acumulado no puede ser mayor al valor total."
            )
            st.rerun()
        ex = float(st.session_state.get("ap_fin_extra_payment") or 0)
        if ex > 0 and not can_add_extra:
            st.session_state["_ap_fin_save_error"] = (
                "No hay saldo pendiente; no puedes registrar otro abono."
            )
            st.rerun()
        if ex > 0 and ex > pend_ui + 0.01:
            st.session_state["_ap_fin_save_error"] = (
                f"El abono adicional ({format_cop(ex)}) supera el saldo pendiente ({format_cop(pend_ui)})."
            )
            st.rerun()
        err_save: Optional[str] = None
        with st.spinner("Guardando montos y abonos…"):
            ok, code, data = api_client.patch_appointment_financials(
                appt_id,
                float(total_amount),
                float(current_deposit),
                float(max(pending, 0)),
            )
            if not ok:
                err_save = f"Error HTTP {code}: {format_http_error_detail(data)}"
            elif ex > 0:
                note_s = (st.session_state.get("ap_fin_extra_note") or "").strip()
                ok_pay, code_pay, data_pay = api_client.post_appointment_payment(
                    appt_id,
                    ex,
                    note_s or None,
                )
                if not ok_pay:
                    err_save = f"No se pudo registrar abono (HTTP {code_pay}): {format_http_error_detail(data_pay)}"
        if err_save:
            st.session_state["_ap_fin_save_error"] = err_save
            st.rerun()
        st.session_state.pop("_ap_fin_save_error", None)
        st.session_state.pop(f"{KEY_FIN_PAYMENTS_PFX}{appt_id}", None)
        purge_appointment_receipt_caches()
        if ex > 0:
            queue_appointment_action_success(
                "**Montos y abonos actualizados.** Hay un nuevo recibo PDF en **Recibos**."
            )
        else:
            queue_appointment_action_success(
                "**Montos actualizados** (valor total del trabajo y saldos)."
            )
        st.session_state["_ap_reload"] = True
        st.session_state.pop("_ap_fin_item", None)
        st.session_state.pop("ap_fin_total", None)
        st.session_state.pop("ap_fin_extra_payment", None)
        st.session_state.pop("ap_fin_extra_note", None)
        st.session_state.pop("_ap_fin_dialog_appt_id", None)
        st.rerun()
@st.dialog("Recibos de pago (PDF)", width="large", dismissible=False)
def dialog_recibos_cita() -> None:
    appt = st.session_state.get("_ap_receipts_item") or {}
    appt_id = int(appt.get("id", 0) or 0)
    if appt_id <= 0:
        st.error("No se encontró la cita.")
        if st.button("Cerrar", use_container_width=True, key="ap_rec_close_bad"):
            st.session_state.pop("_ap_receipts_item", None)
            st.rerun()
        return
    name = str(appt.get("customer_name") or appt.get("name") or "").strip()
    st.markdown(f"**Cita #{appt_id}** · {name or '—'}")
    st.caption(
        "Si al crear la cita hubo abono y el servicio es **tatuaje** (u otro no piercing), se genera un recibo inicial; "
        "en **piercing / limpieza / cambio** no se envía recibo PDF al agendar (solo notificación de cita). "
        "Cada abono adicional puede generar otro PDF. Los archivos se guardan en el servidor."
    )

    list_key = f"{KEY_RECEIPTS_LIST_PFX}{appt_id}"
    cached = st.session_state.get(list_key)
    if not isinstance(cached, tuple) or len(cached) != 3:
        with st.spinner("Cargando índice de recibos…"):
            ok, code, data = api_client.get_appointment_receipts(appt_id)
        st.session_state[list_key] = (ok, code, data)
    ok, code, data = st.session_state[list_key]
    if not ok:
        st.error(f"No se pudieron listar los recibos (HTTP {code}): {format_http_error_detail(data)}")
        if st.button("Cerrar", use_container_width=True, key="ap_rec_close_list_err"):
            st.session_state.pop(list_key, None)
            st.session_state.pop("_ap_receipts_item", None)
            st.rerun()
        return

    rows: List[Dict[str, Any]] = []
    if isinstance(data, list):
        rows = [x for x in data if isinstance(x, dict)]

    if not rows:
        st.info("Todavía no hay recibos registrados para esta cita.")

    for r in rows:
        rid = int(r.get("id", 0) or 0)
        if rid <= 0:
            continue
        kind = str(r.get("kind") or "")
        kind_es = "Agenda / primer abono" if kind == "inicial" else "Abono adicional"
        try:
            amt = float(r.get("amount") or 0)
        except (TypeError, ValueError):
            amt = 0.0
        when = str(r.get("created_at") or "")
        if len(when) >= 19:
            when = when[:19]
        st.markdown(f"**{kind_es}** · {when or '—'} · **{format_cop(amt)}**")

        pdf_key = f"{KEY_RECEIPT_PDF_PFX}{appt_id}_{rid}"
        if pdf_key not in st.session_state:
            ok_pdf, _pc, blob, fname = api_client.fetch_appointment_receipt_pdf(appt_id, rid)
            if ok_pdf and blob:
                st.session_state[pdf_key] = (blob, fname)
        got = st.session_state.get(pdf_key)
        if isinstance(got, tuple) and len(got) == 2 and got[0]:
            blob, fname = got[0], got[1]
            st.download_button(
                "Descargar PDF",
                data=blob,
                file_name=str(fname or f"recibo_{appt_id}_{rid}.pdf"),
                mime="application/pdf",
                use_container_width=True,
                key=f"ap_rec_dl_{appt_id}_{rid}",
            )
        else:
            st.caption("No se pudo cargar el archivo PDF.")
        st.divider()

    if st.button("Cerrar", use_container_width=True, key="ap_rec_close_main"):
        st.session_state.pop("_ap_receipts_item", None)
        st.rerun()

__all__ = ['cleanup_reprogram_dialog_state','dialog_ajustar_montos','dialog_cancelar_cita','dialog_reprogramar_cita','dialog_recibos_cita']
