"""Overflow del día, diálogo cita única y ficha de edición desde calendario."""

from __future__ import annotations

import html as html_mod
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Optional

import streamlit as st

from streamlit_app import api_client
from streamlit_app.appointment_agenda_slots import MIN_BOOKING_DURATION_SLOTS, duration_slots_for_existing_appointment
from streamlit_app.appointment_dates import (
    appointment_time_hm,
    combine_appointment_datetime,
    format_appointment_created_at_display,
)
from streamlit_app.appointment_staff_labels import assigned_artist_display_name
from streamlit_app.appointment_slots import (
    appointment_last_start_slot,
    duration_slots_from_start_last,
    parse_existing_appointment_slot,
    time_slot_options,
)
from streamlit_app.components.appointment_payments_block import render_appointment_abonos_section
from streamlit_app.state.appointment_keys import KEY_RECEIPT_PDF_PFX
from streamlit_app.components.calendar_cells import calendar_overflow_row_html
from streamlit_app.components.pills import row_is_priority, status_pill_html

CAL_FOCUS_SESSION_KEY = "_cal_focus_sheet_deps"


@dataclass(frozen=True)
class CalendarFocusDeps:
    panel_is_technician_role: Callable[[], bool]
    clear_calendar_dialog_focus: Callable[[], None]
    open_firma_contrato_nav: Callable[[dict[str, Any], int], None]
    firmar_contrato_disabled: Callable[[dict[str, Any]], bool]
    firmar_contrato_button_label: Callable[[dict[str, Any]], str]
    reprogram_disabled_for_row: Callable[[dict[str, Any]], bool]
    appointment_detail_plain_body: Callable[[str], str]
    split_design_obs_plain: Callable[[str], tuple[str, str]]
    rebuild_detail_for_patch: Callable[..., str]
    ensure_assignable_staff: Callable[[], list[dict[str, Any]]]
    work_kind_to_assignee_role: Callable[[str], str]
    work_kind_infer_from_existing_row: Callable[[dict[str, Any]], str]
    find_appointment_row_by_id: Callable[[int], Optional[dict[str, Any]]]
    parse_date: Callable[[Any], date]
    get_appointment_payments_cached: Callable[[int], tuple[bool, int, Any]]
    purge_appointment_payment_caches: Callable[[], None]
    queue_appointment_action_success: Callable[[str], None]
    api_error: Callable[[Any], str]
    receipts_cache_prefix: str
    fin_payments_cache_prefix: str


def _deps() -> CalendarFocusDeps:
    d = st.session_state.get(CAL_FOCUS_SESSION_KEY)
    if isinstance(d, CalendarFocusDeps):
        return d
    raise RuntimeError("CalendarFocusDeps: falta configuración (usa set_calendar_focus_session_deps).")


def set_calendar_focus_session_deps(deps: CalendarFocusDeps) -> None:
    st.session_state[CAL_FOCUS_SESSION_KEY] = deps


def clear_calendar_focus_session_deps() -> None:
    st.session_state.pop(CAL_FOCUS_SESSION_KEY, None)


def _calendar_overflow_day_sheet_link_row(
    r: dict[str, Any],
    hist_counts: dict[str, int],
    *,
    key_suffix: str,
) -> None:
    """Resumen rápido + acceso al panel único de ficha/detalle."""
    st.markdown(calendar_overflow_row_html(r, hist_counts), unsafe_allow_html=True)
    aid = int(r.get("id", 0) or 0)
    c1, c2 = st.columns([1, 4])
    with c1:
        if st.button("Ficha completa", use_container_width=True, key=f"cal_day_open_sheet_{key_suffix}"):
            st.session_state["_cal_focus_appt_id"] = aid
            st.session_state.pop("_cal_overflow_day", None)
            st.rerun()




def render_calendar_focus_appointment_body(r: dict[str, Any], hist_counts: dict[str, int]) -> None:
    """Formulario único para ver/editar cita desde calendario (rejilla día / semana)."""
    deps = _deps()
    aid = int(r.get("id", 0) or 0)
    if aid <= 0:
        return
    status_l = str(r.get("status") or "Agendada").strip()
    montos_locked = aid <= 0 or status_l not in {"Agendada", "Reprogramada"}
    firmar_disabled = deps.firmar_contrato_disabled(r)
    firma_lbl = deps.firmar_contrato_button_label(r)
    tech = deps.panel_is_technician_role()
    aid_s = str(aid)

    if tech:
        st.markdown(calendar_overflow_row_html(r, hist_counts), unsafe_allow_html=True)
        if st.button(firma_lbl, use_container_width=True, key=f"fcd_tech_{aid_s}_firma", disabled=firmar_disabled):
            deps.clear_calendar_dialog_focus()
            deps.open_firma_contrato_nav(r, aid)
        return

    seed_k = "_fcd_seed_appt_id"
    slot_opts = time_slot_options()
    today_d = date.today()
    if st.session_state.get(seed_k) != aid:
        st.session_state[seed_k] = aid
        _, sl0 = parse_existing_appointment_slot(r.get("appointment_date", r.get("date")))
        if sl0 not in slot_opts and slot_opts:
            sl0 = slot_opts[0]
        dur0 = duration_slots_for_existing_appointment(r)
        last0 = appointment_last_start_slot(sl0, dur0, slot_opts)
        if last0 not in slot_opts:
            last0 = sl0
        plain = deps.appointment_detail_plain_body(str(r.get("detail") or ""))
        dz0, obs0 = deps.split_design_obs_plain(plain)
        st.session_state[f"fcd_start_{aid_s}"] = sl0
        st.session_state[f"fcd_last_{aid_s}"] = last0
        st.session_state[f"fcd_pri_{aid_s}"] = bool(row_is_priority(r))
        st.session_state[f"fcd_tot_{aid_s}"] = max(
            0, int(round(float(r.get("total_amount") or 0)))
        )
        st.session_state[f"fcd_dz_{aid_s}"] = dz0
        st.session_state[f"fcd_obs_{aid_s}"] = obs0
        wk_here = deps.work_kind_infer_from_existing_row(r)
        role_need = deps.work_kind_to_assignee_role(wk_here)
        staff_opts = [s for s in deps.ensure_assignable_staff() if str(s.get("role")) == role_need]
        if not staff_opts:
            staff_opts = list(deps.ensure_assignable_staff())
        lbls_o: dict[int, str] = {}
        opt_ids_o: list[int] = []
        for s in staff_opts:
            try:
                oid = int(s.get("id") or 0)
            except (TypeError, ValueError):
                continue
            if oid <= 0:
                continue
            opt_ids_o.append(oid)
            fn = str(s.get("first_name") or "").strip()
            ln = str(s.get("last_name") or "").strip()
            lab = (fn + " " + ln).strip() or str(s.get("username") or f"#{oid}")
            lbls_o[oid] = lab + f" (@{s.get('username') or oid})"
        cur_id: Optional[int] = None
        raw_as = r.get("assigned_panel_user_id")
        if raw_as not in (None, "", 0):
            try:
                cur_id = int(raw_as)
            except (TypeError, ValueError):
                cur_id = None
        if cur_id is not None and cur_id > 0 and cur_id not in lbls_o:
            lbls_o[cur_id] = assigned_artist_display_name(r) + " (historial)"
            opt_ids_o = [cur_id] + [x for x in opt_ids_o if x != cur_id]
        pick_art = cur_id if cur_id is not None and cur_id in lbls_o else (opt_ids_o[0] if opt_ids_o else None)
        st.session_state[f"fcd_artpick_{aid_s}"] = int(pick_art) if pick_art is not None else 0

        day_appt, hm_orig = parse_existing_appointment_slot(r.get("appointment_date", r.get("date")))
        hm_eff = hm_orig if hm_orig != "—" else "09:00"
        dt_orig = combine_appointment_datetime(day_appt, hm_eff)
        base = {
            "start": sl0,
            "last": last0,
            "prio": bool(row_is_priority(r)),
            "tot": max(0, int(round(float(r.get("total_amount") or 0)))),
            "artist": pick_art,
            "dz": dz0,
            "obs": obs0,
            "dt_orig": dt_orig,
            "dur": dur0,
        }
        st.session_state[f"fcd_base_{aid_s}"] = base

    st.markdown('<div class="ap-ficha-panel-root" aria-hidden="true"></div>', unsafe_allow_html=True)

    hdr_l, hdr_r = st.columns([3, 2])
    with hdr_l:
        st.markdown("### Cita")
    with hdr_r:
        st.markdown(
            f"<div style='text-align:right'>{format_appointment_created_at_display(r.get('created_at'))}<br>"
            f"{status_pill_html(status_l)}</div>",
            unsafe_allow_html=True,
        )

    st.markdown('<p class="ap-ficha-section-band">Cliente</p>', unsafe_allow_html=True)

    cust: Optional[dict[str, Any]] = None
    try:
        cid_raw = r.get("customer_id")
        if cid_raw:
            cid = int(cid_raw)
            ok_c, _, cdata = api_client.get_customer(cid)
            if ok_c and isinstance(cdata, dict):
                cust = cdata
    except (TypeError, ValueError):
        cust = None

    if cust:
        nm = (
            str(cust.get("first_name") or "").strip() + " " + str(cust.get("last_name") or "").strip()
        ).strip() or str(r.get("customer_name") or "").strip()
        doc_lbl = str(cust.get("document_type") or "CC")
        doc_n = str(cust.get("document_number") or "—").strip()
        em = str(cust.get("email") or "—").strip()
        cel = str(cust.get("phone_number") or r.get("phone") or "—").strip()
        st.markdown(f"**Cliente:** {html_mod.escape(nm or '—')}")
        st.caption(f"{doc_lbl} {doc_n} · ✉ {em} · 📱 {cel}")
    else:
        nm2 = str(r.get("customer_name") or r.get("name") or "—").strip()
        cel2 = str(r.get("phone") or "—").strip()
        st.markdown(f"**Cliente:** {html_mod.escape(nm2)} _(sin cliente vinculado o no cargado)_")
        st.caption(f"📱 Teléfono en cita: **{cel2}**")

    repro_lock = deps.reprogram_disabled_for_row(r) or status_l in {"Cancelada", "Finalizada"}
    st.markdown('<p class="ap-ficha-section-band">Horario</p>', unsafe_allow_html=True)
    h_sched_a, h_sched_b = st.columns(2, vertical_alignment="center")
    h_sched_a.markdown(
        '<span class="ap-ficha-col-head ap-ficha-col-head--wide">Desde (inicio)</span>',
        unsafe_allow_html=True,
    )
    h_sched_b.markdown(
        '<span class="ap-ficha-col-head ap-ficha-col-head--wide">Hasta (última franja ocupada)</span>',
        unsafe_allow_html=True,
    )
    t1a, t1b = st.columns(2)
    with t1a:
        st.selectbox(
            "Desde (inicio)",
            options=slot_opts,
            disabled=repro_lock,
            key=f"fcd_start_{aid_s}",
        )
    with t1b:
        st.selectbox(
            "Hasta (última franja ocupada)",
            options=slot_opts,
            disabled=repro_lock,
            key=f"fcd_last_{aid_s}",
        )
    if repro_lock:
        st.caption("Horario bloqueado: estado cerrado o la cita no admite cambio de franja desde aquí.")

    st.markdown('<p class="ap-ficha-section-band">Cita · servicio</p>', unsafe_allow_html=True)
    rc_key = f"{deps.receipts_cache_prefix}{aid}"
    cached_r = st.session_state.get(rc_key)
    if not isinstance(cached_r, tuple) or len(cached_r) != 3:
        cached_r = api_client.get_appointment_receipts(aid)
        st.session_state[rc_key] = cached_r
    ok_rr, _, rrows = cached_r
    rec_txt = "—"
    if ok_rr and isinstance(rrows, list):
        ids_r = sorted(
            int(x.get("id") or 0) for x in rrows if isinstance(x, dict) and int(x.get("id") or 0)
        )
        if ids_r:
            rec_txt = ", ".join(str(x) for x in ids_r)
    st.caption(f"**Recibo id(s)** — solo lectura: {rec_txt}")

    artist_locked = bool(r.get("has_signed_contract"))
    lbls_reload = {}
    role_need_r = deps.work_kind_to_assignee_role(deps.work_kind_infer_from_existing_row(r))
    staff_reload = [s for s in deps.ensure_assignable_staff() if str(s.get("role")) == role_need_r] or list(
        deps.ensure_assignable_staff()
    )
    opt_ids_reload: list[int] = []
    for s in staff_reload:
        try:
            oid = int(s.get("id") or 0)
        except (TypeError, ValueError):
            continue
        if oid <= 0:
            continue
        fn = str(s.get("first_name") or "").strip()
        ln = str(s.get("last_name") or "").strip()
        lab = ((fn + " " + ln).strip() or str(s.get("username") or oid)) + f" (@{s.get('username') or oid})"
        lbls_reload[oid] = lab
        opt_ids_reload.append(oid)

    sel_art = int(st.session_state.get(f"fcd_artpick_{aid_s}") or 0)
    if sel_art not in lbls_reload and sel_art > 0:
        lbls_reload[sel_art] = assigned_artist_display_name(r)
        opt_ids_reload = [sel_art] + [x for x in opt_ids_reload if x != sel_art]
    ix_def = (
        opt_ids_reload.index(sel_art)
        if sel_art in opt_ids_reload
        else 0
    )

    svc_left, svc_right = st.columns(2, gap="medium")
    with svc_left:
        if not opt_ids_reload:
            st.warning("No hay artistas configurados en el panel para este tipo de servicio.")
        else:
            st.selectbox(
                "Artista",
                options=opt_ids_reload,
                index=min(ix_def, max(0, len(opt_ids_reload) - 1)),
                format_func=lambda i: lbls_reload.get(int(i), str(i)),
                disabled=montos_locked or artist_locked,
                key=f"fcd_artpick_{aid_s}",
            )
        st.number_input(
            "Valor del tatuaje / trabajo (COP, entero)",
            min_value=0.0,
            step=10000.0,
            disabled=montos_locked,
            key=f"fcd_tot_{aid_s}",
            format="%.0f",
            help="Sin mínimo de agendamiento; el abonado acumulado no puede superar este total.",
        )
        _ = st.checkbox("Cita prioritaria", disabled=montos_locked, key=f"fcd_pri_{aid_s}")
        if artist_locked:
            st.caption("El artista no se puede cambiar si ya existe contrato firmado en esta cita.")
    with svc_right:
        _ = st.text_area(
            "Descripción del diseño",
            disabled=montos_locked,
            height=120,
            key=f"fcd_dz_{aid_s}",
        )
        _ = st.text_area(
            "Observaciones",
            disabled=montos_locked,
            height=100,
            key=f"fcd_obs_{aid_s}",
        )

    render_appointment_abonos_section(
        aid=aid,
        appointment_row=deps.find_appointment_row_by_id(aid) or r,
        montos_locked=montos_locked,
        today=today_d,
        get_payments_cached=deps.get_appointment_payments_cached,
        purge_payment_caches=deps.purge_appointment_payment_caches,
        fin_payments_cache_prefix=deps.fin_payments_cache_prefix,
        receipts_cache_prefix=deps.receipts_cache_prefix,
        receipt_pdf_cache_prefix=KEY_RECEIPT_PDF_PFX,
        queue_success=deps.queue_appointment_action_success,
        api_error=deps.api_error,
        seed_reload_key=seed_k,
    )

    b_now = dict(st.session_state.get(f"fcd_base_{aid_s}") or {})
    cur_start_s = str(st.session_state.get(f"fcd_start_{aid_s}") or "")
    cur_last_s = str(st.session_state.get(f"fcd_last_{aid_s}") or "")
    cur_pri_b = bool(st.session_state.get(f"fcd_pri_{aid_s}") or False)
    cur_tot_f = float(st.session_state.get(f"fcd_tot_{aid_s}") or 0)
    cur_art_i = int(st.session_state.get(f"fcd_artpick_{aid_s}") or 0)
    dz_cur = str(st.session_state.get(f"fcd_dz_{aid_s}") or "")
    obs_cur = str(st.session_state.get(f"fcd_obs_{aid_s}") or "")
    dur_now = (
        duration_slots_from_start_last(cur_start_s, cur_last_s, slot_opts)
        if cur_start_s in slot_opts and cur_last_s in slot_opts
        else int(b_now.get("dur") or MIN_BOOKING_DURATION_SLOTS)
    )
    ds_day_appt, hm_row = parse_existing_appointment_slot(r.get("appointment_date", r.get("date")))
    new_booking_dt = (
        combine_appointment_datetime(ds_day_appt, cur_start_s) if cur_start_s != "—" else str(b_now.get("dt_orig") or "")
    )
    base_dur = int(b_now.get("dur") or MIN_BOOKING_DURATION_SLOTS)
    sched_need = montos_locked is False and (
        (cur_start_s, cur_last_s) != (b_now.get("start"), b_now.get("last"))
        or dur_now != base_dur
        or (new_booking_dt and new_booking_dt != str(b_now.get("dt_orig") or ""))
    )
    text_dirty = dz_cur != str(b_now.get("dz") or "") or obs_cur != str(b_now.get("obs") or "")
    art_dirty = cur_art_i != int(b_now.get("artist") or 0)
    prio_dirty = cur_pri_b != bool(b_now.get("prio"))
    tot_dirty_cop = (
        montos_locked is False and int(round(cur_tot_f)) != int(b_now.get("tot") or 0)
    )
    form_dirty = bool(b_now) and (
        sched_need or text_dirty or art_dirty or prio_dirty or tot_dirty_cop
    )

    st.divider()
    st.markdown("##### Acciones")

    leave_confirm = bool(st.session_state.get(f"fcd_confirm_leave_{aid_s}"))
    if leave_confirm:
        st.warning("Hay cambios sin guardar. Si sales ahora se descartan en esta pantalla (no en el servidor).")
        cx1, cx2 = st.columns(2)
        with cx1:
            if st.button("Salir sin guardar", use_container_width=True, key=f"fcd_lvy_{aid_s}"):
                st.session_state.pop(f"fcd_confirm_leave_{aid_s}", None)
                st.session_state.pop(seed_k, None)
                deps.clear_calendar_dialog_focus()
                st.rerun()
        with cx2:
            if st.button("Seguir editando", use_container_width=True, key=f"fcd_lvn_{aid_s}"):
                st.session_state.pop(f"fcd_confirm_leave_{aid_s}", None)
                st.rerun()
        return

    detail_for_save = deps.rebuild_detail_for_patch(r, dz_cur, obs_cur, agenda_slots_override=dur_now)
    detail_meta_only = detail_for_save if (not sched_need and text_dirty) else None

    if montos_locked is False:

        def _fcd_save_all() -> None:
            if tot_dirty_cop:
                nf = deps.find_appointment_row_by_id(aid) or r
                dep_live = float(nf.get("deposit") or 0)
                ttot = float(int(round(cur_tot_f)))
                if dep_live > ttot + 0.01:
                    st.toast("El valor total no puede ser menor que lo ya abonado.", icon="⚠️")
                    return
                pend = round(ttot - dep_live, 2)
                ok_t, ct, bt = api_client.patch_appointment_financials(aid, ttot, dep_live, pend)
                if not ok_t:
                    st.toast(f"Montos (HTTP {ct}): {deps.api_error(bt)}", icon="❌")
                    return
            if sched_need:
                ok_s, cs, bs = api_client.patch_appointment_reschedule(aid, new_booking_dt, detail_for_save)
                if not ok_s:
                    st.toast(f"Horario (HTTP {cs}): {deps.api_error(bs)}", icon="❌")
                    return
            meta_need = art_dirty or prio_dirty or detail_meta_only is not None
            if meta_need:
                ok_m, cm, bm = api_client.patch_appointment_meta(
                    aid,
                    assigned_panel_user_id=(cur_art_i if art_dirty else None),
                    is_priority=cur_pri_b,
                    detail=detail_meta_only,
                )
                if not ok_m:
                    st.toast(f"Servicio/meta (HTTP {cm}): {deps.api_error(bm)}", icon="❌")
                    return
            st.session_state.pop(seed_k, None)
            st.session_state["_ap_reload"] = True
            deps.queue_appointment_action_success("**Cambios guardados en la cita.**")
            st.rerun()

        repro_btn_disabled = deps.reprogram_disabled_for_row(r)
        ba1, ba2, ba3, ba4 = st.columns(4)
        with ba1:
            if st.button("Guardar cambios", type="primary", use_container_width=True, key=f"fcd_sv_{aid_s}"):
                _fcd_save_all()
        with ba2:
            if st.button(
                "Reprogramar",
                use_container_width=True,
                disabled=repro_btn_disabled,
                key=f"fcd_repr_{aid_s}",
                help="Abre el formulario de nueva fecha y franja (con disponibilidad del profesional).",
            ):
                st.session_state.pop(seed_k, None)
                st.session_state.pop("_cal_focus_appt_id", None)
                deps.clear_calendar_dialog_focus()
                st.session_state["_ap_reprogram_item"] = dict(r)
                st.rerun()
        with ba3:
            anular_disabled = aid <= 0 or status_l in {"Cancelada", "Finalizada"}
            if st.button(
                "Cancelar cita",
                use_container_width=True,
                disabled=anular_disabled,
                key=f"fcd_can_{aid_s}",
            ):
                st.session_state.pop(seed_k, None)
                st.session_state.pop("_cal_focus_appt_id", None)
                st.session_state["_ap_cancel_item"] = dict(r)
                st.rerun()
        with ba4:
            if st.button(
                firma_lbl,
                disabled=firmar_disabled,
                use_container_width=True,
                key=f"fcd_fr_{aid_s}",
            ):
                deps.clear_calendar_dialog_focus()
                deps.open_firma_contrato_nav(dict(r), aid)

        if st.button("Cerrar", use_container_width=True, key=f"fcd_close_{aid_s}"):
            if form_dirty:
                st.session_state[f"fcd_confirm_leave_{aid_s}"] = True
                st.rerun()
            st.session_state.pop(seed_k, None)
            deps.clear_calendar_dialog_focus()
            st.rerun()
    else:
        if st.button("Cerrar", use_container_width=True, key=f"fcd_close_ro_{aid_s}"):
            st.session_state.pop(seed_k, None)
            deps.clear_calendar_dialog_focus()
            st.rerun()


@st.dialog("Citas del día", width="large", dismissible=False)
def dialog_calendar_day_appointments(
    buckets: dict[tuple[int, int, int], list[dict[str, Any]]],
    hist_counts: dict[str, int],
) -> None:
    """Lista del día: tarjetas HTML en un solo bloque + botones en pasada aparte (menos flash al scroll)."""
    tup = st.session_state.get("_cal_overflow_day")
    if not tup:
        return
    deps = _deps()
    y, m, d = int(tup[0]), int(tup[1]), int(tup[2])
    day_rows = list(buckets.get((y, m, d), []))
    day_date = date(y, m, d)
    if not day_rows:
        st.info("No hay citas para este día con los filtros actuales.")
        if st.button("Cerrar", key="cal_dlg_close_empty", use_container_width=True):
            deps.clear_calendar_dialog_focus()
            st.rerun()
        return

    st.markdown(f"**{day_date.strftime('%d/%m/%Y')}** · **{len(day_rows)}** cita(s)")
    if deps.panel_is_technician_role():
        st.caption(
            "Como **tatuador / perforador** solo puedes usar **Completar firma profesional**. "
            "El agendamiento, montos y reprogramación los gestiona administración o ventas."
        )
    else:
        st.caption(
            "**Firmar contrato** abre la vista de firma. "
            "Reprogramar, Montos o Recibos cierran este panel y abren el formulario correspondiente."
        )

    all_cards = "".join(
        f'<div class="appt-card-wrap">{calendar_overflow_row_html(r, hist_counts)}</div>'
        for r in day_rows
    )
    st.markdown(f'<div class="appt-cards-block">{all_cards}</div>', unsafe_allow_html=True)

    st.markdown("---")
    tech = deps.panel_is_technician_role()

    for idx, r in enumerate(day_rows):
        appt_id = int(r.get("id", 0) or 0)
        status = str(r.get("status") or "Agendada")
        nm = str(r.get("customer_name") or r.get("name") or "").strip() or "—"
        hm = appointment_time_hm(r.get("appointment_date", r.get("date")))
        st.caption(f"{hm} · {nm}")

        firmar_disabled = deps.firmar_contrato_disabled(r)
        repro_disabled = deps.reprogram_disabled_for_row(r)
        montos_disabled = appt_id <= 0 or status not in {"Agendada", "Reprogramada"}
        anular_disabled = appt_id <= 0 or status in {"Cancelada", "Finalizada"}
        key_base = f"{appt_id}_{y}_{m}_{d}_{idx}"

        if tech:
            lbl = deps.firmar_contrato_button_label(r)
            if st.button(
                lbl,
                disabled=firmar_disabled,
                use_container_width=True,
                key=f"cal_dlg_firmar_{key_base}",
            ):
                deps.clear_calendar_dialog_focus()
                deps.open_firma_contrato_nav(r, appt_id)
        else:
            b0, b1, b2, b3, b4 = st.columns(5)
            with b0:
                if st.button(
                    "Firmar contrato",
                    disabled=firmar_disabled,
                    use_container_width=True,
                    key=f"cal_dlg_firmar_{key_base}",
                ):
                    deps.clear_calendar_dialog_focus()
                    deps.open_firma_contrato_nav(r, appt_id)
            with b1:
                if st.button(
                    "Reprogramar",
                    disabled=repro_disabled,
                    use_container_width=True,
                    key=f"cal_dlg_repr_{key_base}",
                ):
                    deps.clear_calendar_dialog_focus()
                    st.session_state["_ap_reprogram_item"] = r
                    st.rerun()
            with b2:
                if st.button(
                    "Montos",
                    disabled=montos_disabled,
                    use_container_width=True,
                    key=f"cal_dlg_fin_{key_base}",
                ):
                    deps.clear_calendar_dialog_focus()
                    st.session_state["_ap_fin_item"] = r
                    st.rerun()
            with b3:
                if st.button(
                    "Recibos",
                    disabled=appt_id <= 0,
                    use_container_width=True,
                    key=f"cal_dlg_rec_{key_base}",
                ):
                    deps.clear_calendar_dialog_focus()
                    st.session_state["_ap_receipts_item"] = r
                    st.rerun()
            with b4:
                if st.button(
                    "Anular",
                    disabled=anular_disabled,
                    use_container_width=True,
                    key=f"cal_dlg_can_{key_base}",
                ):
                    deps.clear_calendar_dialog_focus()
                    st.session_state["_ap_cancel_item"] = r
                    st.rerun()

        if idx < len(day_rows) - 1:
            st.markdown('<div class="cal-day-action-sep"></div>', unsafe_allow_html=True)

    st.markdown("---")
    if st.button("Cerrar", key="cal_dlg_close", use_container_width=True):
        deps.clear_calendar_dialog_focus()
        st.rerun()


@st.dialog("Cita", width="large", dismissible=False)
def dialog_calendar_single_appointment(
    _buckets: dict[tuple[int, int, int], list[dict[str, Any]]],
    hist_counts: dict[str, int],
) -> None:
    """Diálogo para una sola cita (desde ▸ en rejilla semanal o mes)."""
    raw_id = st.session_state.get("_cal_focus_appt_id")
    try:
        aid = int(raw_id)
    except (TypeError, ValueError):
        aid = 0
    if aid <= 0:
        return
    deps = _deps()
    r = deps.find_appointment_row_by_id(aid)
    if not r:
        st.warning(
            "No se encontró la cita en la lista actual. Pulsa **Actualizar** o abre de nuevo desde el calendario."
        )
        if st.button("Cerrar", key="cal_single_close_nf", use_container_width=True):
            deps.clear_calendar_dialog_focus()
            st.rerun()
        return
    try:
        day_date = deps.parse_date(r.get("appointment_date", r.get("date")))
    except (TypeError, ValueError):
        day_date = date.today()
    st.markdown(f"**{day_date.strftime('%d/%m/%Y')}** · Cita **#{aid}**")
    if deps.panel_is_technician_role():
        st.caption(
            "Como **tatuador / perforador** solo ves citas **desde hoy** con estado activo; aquí solo puedes "
            "**Completar firma profesional** cuando recepción ya guardó el contrato del cliente."
        )
    render_calendar_focus_appointment_body(r, hist_counts)
