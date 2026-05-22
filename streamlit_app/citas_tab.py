"""Streamlit: Citas con calendario, franjas horarias y formulario mínimo."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, Optional

import streamlit as st

from app.domain.contract_kinds import service_type_requires_contract
from app.domain.contract_signing_guard import appointment_must_be_fully_paid_for_contract
from streamlit_app import api_client

from streamlit_app.appointment_agenda_slots import (
    AGENDA_SLOTS_DETAIL_PATTERN as _AGENDA_SLOTS_DETAIL_PATTERN,
    MAX_BOOKING_DURATION_SLOTS as _MAX_BOOKING_DURATION_SLOTS,
    MIN_BOOKING_DURATION_SLOTS as _MIN_BOOKING_DURATION_SLOTS,
    append_agenda_slots_marker as _append_agenda_slots_marker,
    duration_slots_for_existing_appointment as _duration_slots_for_existing_appointment,
)
from streamlit_app.appointment_dates import appointment_row_date as _parse_date
from streamlit_app.appointment_filters import filter_appointment_rows
from streamlit_app.store_choices import load_store_choices
from streamlit_app.appointment_staff_labels import assigned_artist_display_name as _assigned_artist_display_name
from streamlit_app.components.calendar_focus_dialogs import (
    CalendarFocusDeps,
    clear_calendar_focus_session_deps,
    dialog_calendar_day_appointments,
    dialog_calendar_single_appointment,
    set_calendar_focus_session_deps,
)
from streamlit_app.components.calendar_main_month import render_main_calendar as _render_main_calendar_impl
from streamlit_app.components.calendar_query_nav import inject_calendar_query_nav_bridge
from streamlit_app.components.calendar_week_schedule import render_week_schedule_grid, week_monday as _monday_of_week
from streamlit_app.components.citas_legend import render_citas_color_legend as _render_citas_color_legend
from streamlit_app.components.pills import client_history_key as _client_history_key
from streamlit_app.citas_agendar_dialog import (
    dialog_agendar_cita,
    pop_booking_document_session as _pop_booking_document_session,
    queue_appointment_action_success as _queue_appointment_action_success,
)
from streamlit_app.citas_booking_meta import (
    service_and_detail_for_work_kind,
    work_kind_infer_from_existing_row,
    work_kind_to_assignee_role,
)
from streamlit_app.citas_appointment_search import dialog_buscar_cita
from streamlit_app.citas_detail_dialogs import (
    dialog_ajustar_montos,
    dialog_cancelar_cita,
    dialog_recibos_cita,
    dialog_reprogramar_cita,
    toast_financial_save_error_if_any,
)
from streamlit_app.citas_panel_staff import ensure_assignable_staff
from streamlit_app.citas_row_policy import reprogram_disabled_for_row
from streamlit_app.http_error_detail import format_http_error_detail
from streamlit_app.panel_navigation import (
    open_contract_artist_signature,
    open_contract_express_piercing,
    open_contract_signing,
)
from streamlit_app.reporte_finanzas_citas import render_reporte_financiero_citas_body
from streamlit_app.state.appointment_cache import (
    get_appointment_payments_cached as _get_appointment_payments_cached,
    purge_appointment_payment_caches as _purge_appointment_payment_caches,
    purge_appointment_receipt_caches as _purge_appointment_receipt_caches,
)
from streamlit_app.state.appointment_keys import (
    KEY_ACTION_INFO,
    KEY_FIN_PAYMENTS_PFX,
    KEY_RECEIPTS_LIST_PFX,
    KEY_TOAST_FETCH_ERR,
)
from streamlit_app.styles.inject import inject_via_streamlit_lazy
from streamlit_app.survey_question_stats_report import render_survey_question_stats_report


def _render_appointment_action_feedback() -> None:
    msg = st.session_state.pop(KEY_ACTION_INFO, None)
    if msg:
        st.toast(msg, icon="✅", duration="long")


def _render_appointments_fetch_error_toast() -> None:
    """Un toast por mensaje de fallo al cargar citas (evita repetir en cada rerun)."""
    err = st.session_state.get("_ap_err")
    if not err:
        st.session_state.pop(KEY_TOAST_FETCH_ERR, None)
        return
    if st.session_state.get(KEY_TOAST_FETCH_ERR) != err:
        st.session_state[KEY_TOAST_FETCH_ERR] = err
        st.toast(str(err), icon="❌", duration="long")


def _may_see_all_appointments() -> bool:
    """Vendedor / administrador / modo env con acceso total ven el listado completo (con filtro opcional)."""
    from streamlit_app.panel_auth import panel_auth_enabled

    if not panel_auth_enabled():
        return True
    if st.session_state.get("_panel_session_full_access"):
        return True
    role = str(st.session_state.get("_panel_user_role") or "")
    return role in ("administrador", "vendedor")


def _panel_is_technician_role() -> bool:
    """Tatuador o perforador: citas activas propias desde hoy; no agenda ni montos ni reprogramar."""
    role = str(st.session_state.get("_panel_user_role") or "")
    return role in ("tatuador", "perforador")


def _appointment_row_active_for_technician(row: dict[str, Any]) -> bool:
    stv = str(row.get("status") or "").strip().lower()
    return stv in ("agendada", "reprogramada")


def _appointment_for_technician_visible_date(row: dict[str, Any], *, ref_day: date) -> bool:
    """Solo citas con fecha de agenda >= día de referencia (típicamente hoy)."""
    ad = _parse_date(row.get("appointment_date", row.get("date")))
    return ad >= ref_day


def _filter_appointments_for_session_role(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Técnicos: estados activos y fecha de cita desde hoy en adelante."""
    if not _panel_is_technician_role():
        return items
    today = date.today()
    return [
        r
        for r in items
        if _appointment_row_active_for_technician(r)
        and _appointment_for_technician_visible_date(r, ref_day=today)
    ]


def _technician_clear_disallowed_dialog_states() -> None:
    """Evita abrir agendar / montos / reprogramar / recibos / anular si el rol es solo técnico."""
    if not _panel_is_technician_role():
        return
    st.session_state.pop("_ap_dlg", None)
    st.session_state.pop("_ap_fin_item", None)
    st.session_state.pop("_ap_reprogram_item", None)
    st.session_state.pop("_ap_cancel_item", None)
    st.session_state.pop("_ap_receipts_item", None)


def _clear_calendar_dialog_focus() -> None:
    """Cierra diálogos de calendario asociados al día o a una cita concreta."""
    st.session_state.pop("_cal_overflow_day", None)
    st.session_state.pop("_cal_focus_appt_id", None)
    clear_calendar_focus_session_deps()


def _find_appointment_row_by_id(appt_id: int) -> Optional[dict[str, Any]]:
    for row in st.session_state.get("_ap_list") or []:
        if int(row.get("id", 0) or 0) == int(appt_id):
            return row
    return None


def _contract_firma_blocked_por_saldo(r: Dict[str, Any]) -> bool:
    """True si hay valor total en la cita y aún queda saldo pendiente (no se puede firmar)."""
    ok, _ = appointment_must_be_fully_paid_for_contract(
        total_amount=r.get("total_amount"),
        deposit=r.get("deposit"),
        pending_balance=r.get("pending_balance"),
    )
    return not ok


def _firmar_contrato_disabled(r: Dict[str, Any]) -> bool:
    """Recepción no reabre tras registrar contrato; el técnico sí puede completar su firma pendiente."""
    appt_id = int(r.get("id", 0) or 0)
    status = str(r.get("status") or "Agendada")
    has_customer = r.get("customer_id") is not None
    base = (
        appt_id <= 0
        or not has_customer
        or status in {"Cancelada", "Finalizada"}
        or not service_type_requires_contract(str(r.get("service_type") or ""))
        or _contract_firma_blocked_por_saldo(r)
    )
    if base:
        return True
    has_contract = bool(r.get("has_signed_contract"))
    pending_artist = bool(r.get("contract_pending_artist_signature"))
    if _panel_is_technician_role():
        # El técnico solo completa su firma sobre un contrato ya guardado en recepción (sin datos ni encuesta).
        return base or not pending_artist
    return has_contract


def _firmar_contrato_button_label(r: Dict[str, Any]) -> str:
    """Texto del botón según estado del contrato (requiere `contract_pending_artist_signature` en la API)."""
    has_contract = bool(r.get("has_signed_contract"))
    pending_artist = bool(r.get("contract_pending_artist_signature"))
    if _panel_is_technician_role():
        if pending_artist:
            return "Completar firma profesional"
        if has_contract:
            return "Contrato firmado"
        return "Firma pendiente en recepción"
    if not has_contract:
        return "Firmar contrato"
    if pending_artist:
        return "Pendiente firma profesional"
    return "Contrato firmado"


def _open_firma_contrato_nav(r: Dict[str, Any], appt_id: int) -> None:
    if _panel_is_technician_role():
        if bool(r.get("contract_pending_artist_signature")):
            open_contract_artist_signature(appt_id)
        return
    open_contract_signing(appt_id)


def _appointments_query_assigned_user_id() -> Optional[int]:
    if not _may_see_all_appointments():
        uid = st.session_state.get("_panel_user_id")
        return int(uid) if uid is not None else None
    raw = st.session_state.get("_ap_filter_artist_id")
    if raw is None or raw == 0:
        return None
    return int(raw)



def _artist_filter_labels_and_map() -> tuple[list[str], dict[str, int]]:
    from app.domain.panel_user_profile import PANEL_ROLE_LABEL_ES

    staff = ensure_assignable_staff()
    labels: list[str] = ["Todos"]
    id_by_label: dict[str, int] = {"Todos": 0}
    for s in staff:
        r = str(s.get("role") or "")
        tag = PANEL_ROLE_LABEL_ES.get(r, r)
        lab = (
            f"{s.get('first_name', '')} {s.get('last_name', '')} (@{s.get('username', '')}) — {tag}"
        ).strip()
        if lab in id_by_label:
            lab = f"{lab} · id {s.get('id')}"
        labels.append(lab)
        id_by_label[lab] = int(s["id"])
    return labels, id_by_label


def _appointment_scope_caption() -> None:
    """Texto de alcance cuando el operador no usa filtro de profesional."""
    from app.domain.panel_user_profile import PANEL_ROLE_LABEL_ES

    role_lbl = PANEL_ROLE_LABEL_ES.get(str(st.session_state.get("_panel_user_role") or ""), "operador")
    if _panel_is_technician_role():
        st.caption(
            "Solo ves citas **activas** (agendada / reprogramada) **asignadas a ti**, "
            "**desde hoy en adelante**. "
            f"Rol: **{role_lbl}**."
        )
    else:
        st.caption(f"Solo ves citas asignadas a **tu usuario** del panel. Rol: **{role_lbl}**.")


def _store_filter_format(store_id: int, labels: dict[int, str]) -> str:
    if int(store_id or 0) <= 0:
        return "Todos"
    return labels.get(int(store_id), f"#{store_id}")


def _render_calendar_filters_row(*, svc_values: list[str], status_values: list[str]) -> None:
    """Tienda, servicio, estado y (si aplica) profesional en una sola línea."""
    store_ids, store_labels = load_store_choices()
    store_opts = [0] + list(store_ids)
    may_all = _may_see_all_appointments()

    if may_all:
        labels, id_by_label = _artist_filter_labels_and_map()
        c1, c2, c3, c4 = st.columns([1.15, 1.05, 1.0, 1.35], vertical_alignment="bottom")
        with c1:
            st.selectbox(
                "Tienda",
                options=store_opts,
                format_func=lambda sid: _store_filter_format(sid, store_labels),
                key="_ap_cal_f_store_id",
            )
        with c2:
            st.selectbox("Servicio", options=["Todos", *svc_values], key="_ap_cal_f_service")
        with c3:
            st.selectbox("Estado", options=["Todos", *status_values], key="_ap_cal_f_status")
        with c4:
            choice = st.selectbox(
                "Profesional",
                options=labels,
                key="_ap_filt_artist_cal",
            )
            st.session_state["_ap_filter_artist_id"] = id_by_label.get(str(choice), 0)
    else:
        st.session_state["_ap_filter_artist_id"] = 0
        c1, c2, c3 = st.columns([1.2, 1.1, 1.05], vertical_alignment="bottom")
        with c1:
            st.selectbox(
                "Tienda",
                options=store_opts,
                format_func=lambda sid: _store_filter_format(sid, store_labels),
                key="_ap_cal_f_store_id",
            )
        with c2:
            st.selectbox("Servicio", options=["Todos", *svc_values], key="_ap_cal_f_service")
        with c3:
            st.selectbox("Estado", options=["Todos", *status_values], key="_ap_cal_f_status")
        _appointment_scope_caption()



# Separador explícito entre descripción de diseño y observaciones al editar detalle de cita existente.
_APPT_DESIGN_OBS_DETAIL_SEP = "\n---\n"
_DETAIL_LEADING_BRACKET_TAG = re.compile(r"^\s*\[([^\]\n]{1,64})\]\s*", re.IGNORECASE)


def _appointment_detail_plain_body(detail_full: str) -> str:
    """Quita marcador [agenda_slots:N] y la primera etiqueta tipo [Tatuaje]."""
    d = detail_full or ""
    m = _AGENDA_SLOTS_DETAIL_PATTERN.search(d)
    core = (d[: m.start()] if m else d).strip()
    tm = _DETAIL_LEADING_BRACKET_TAG.match(core)
    if tm:
        core = core[tm.end() :].strip()
    return core


def _split_design_obs_plain(core: str) -> tuple[str, str]:
    if _APPT_DESIGN_OBS_DETAIL_SEP in core:
        a, _, b = core.partition(_APPT_DESIGN_OBS_DETAIL_SEP)
        return a.strip(), b.strip()
    return core.strip(), ""


def _merge_design_obs_plain(design: str, obs: str) -> str:
    dz, nt = design.strip(), obs.strip()
    if dz and nt:
        return f"{dz}{_APPT_DESIGN_OBS_DETAIL_SEP}{nt}"
    return dz or nt


def _rebuild_detail_for_patch(
    row: dict[str, Any],
    design: str,
    obs: str,
    *,
    agenda_slots_override: Optional[int] = None,
) -> str:
    slots = (
        int(agenda_slots_override)
        if agenda_slots_override is not None
        else _duration_slots_for_existing_appointment(row)
    )
    slots = max(_MIN_BOOKING_DURATION_SLOTS, min(_MAX_BOOKING_DURATION_SLOTS, slots))
    wk = work_kind_infer_from_existing_row(row)
    merged = _merge_design_obs_plain(design, obs)
    _, detail_for_api = service_and_detail_for_work_kind(wk, merged)
    return _append_agenda_slots_marker(detail_for_api, slots)


def _consume_cal_nav_component_result() -> None:
    """Lee el resultado del componente cal_nav_bridge y abre el diálogo correspondiente.

    El componente intercepta clics en .cal-query-nav sin navegar por URL,
    evitando la pérdida de sesión. Cada acción lleva un ``_nonce`` único;
    Python lo guarda en ``_cal_nav_consumed_nonce`` para no reprocesar la misma
    acción aunque Streamlit restaure el widget state en reruns posteriores.
    """
    nav = st.session_state.get("cal_nav_bridge")
    if isinstance(nav, dict):
        nonce = nav.get("_nonce")
        if nonce and nonce == st.session_state.get("_cal_nav_consumed_nonce"):
            return  # ya procesado; Streamlit restauró el mismo widget state
        if nonce:
            st.session_state["_cal_nav_consumed_nonce"] = nonce
        action_type = nav.get("type")
        try:
            if action_type == "appt":
                aid = int(nav.get("id", 0) or 0)
                if aid > 0:
                    st.session_state["_cal_focus_appt_id"] = aid
                    st.session_state.pop("_cal_overflow_day", None)
            elif action_type == "book":
                y = int(nav.get("y", 0) or 0)
                m = int(nav.get("m", 0) or 0)
                d = int(nav.get("d", 0) or 0)
                if d > 0:
                    picked = date(y, m, d)
                    if picked >= date.today() and not _panel_is_technician_role():
                        _clear_calendar_dialog_focus()
                        _pop_booking_document_session()
                        st.session_state["ap_ad"] = picked
                        st.session_state["_ap_dlg"] = "create"
        except (ValueError, TypeError):
            pass
        return

    # Fallback: query params directos en la URL (acceso externo con ?cal_appt_id=)
    _consume_cal_appt_query_param()
    _consume_cal_book_query_param()


def _consume_cal_appt_query_param() -> None:
    """Fallback: abre diálogo de cita desde ``?cal_appt_id=`` en la URL."""
    raw = st.query_params.get("cal_appt_id")
    if raw is None:
        return
    try:
        aid = int(str(raw).strip())
        if aid > 0:
            st.session_state["_cal_focus_appt_id"] = aid
            st.session_state.pop("_cal_overflow_day", None)
    except ValueError:
        pass
    try:
        st.query_params.pop("cal_appt_id", None)
    except Exception:
        pass


def _consume_cal_book_query_param() -> None:
    """Fallback: abre agendar cita desde ``?cal_book=YYYY-MM-DD`` en la URL."""
    raw = st.query_params.get("cal_book")
    if raw is None:
        return
    try:
        parts = str(raw).strip().split("-")
        if len(parts) != 3:
            raise ValueError("formato")
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        picked = date(y, m, d)
        if picked < date.today() or _panel_is_technician_role():
            try:
                st.query_params.pop("cal_book", None)
            except Exception:
                pass
            return
        _clear_calendar_dialog_focus()
        _pop_booking_document_session()
        st.session_state["ap_ad"] = picked
        st.session_state["_ap_dlg"] = "create"
    except (ValueError, TypeError):
        pass
    try:
        st.query_params.pop("cal_book", None)
    except Exception:
        pass


def _sync_week_monday_for_agenda_context() -> None:
    """Deja `_ap_week_monday` coherente con el mes abierto en el calendario (o con hoy si es el mismo mes)."""
    ym_raw = st.session_state.get("_ap_cal_ym")
    if isinstance(ym_raw, (list, tuple)) and len(ym_raw) >= 2:
        try:
            y, m = int(ym_raw[0]), int(ym_raw[1])
        except (TypeError, ValueError):
            td = date.today()
            y, m = td.year, td.month
    else:
        td = date.today()
        y, m = td.year, td.month
    today_d = date.today()
    anchor = today_d if (today_d.year == y and today_d.month == m) else date(y, m, 1)
    st.session_state["_ap_week_monday"] = _monday_of_week(anchor).isoformat()


def _appointments_by_day_sorted(items: list[dict[str, Any]]) -> dict[tuple[int, int, int], list[dict[str, Any]]]:
    """Citas agrupadas por día local, ordenadas por hora de inicio."""
    buckets: dict[tuple[int, int, int], list[dict[str, Any]]] = {}

    def sort_key(r: dict[str, Any]) -> tuple[int, int]:
        raw = r.get("appointment_date", r.get("date"))
        if isinstance(raw, datetime):
            return (raw.hour, raw.minute)
        s = str(raw or "").strip().replace("T", " ")
        for chunk, fmt in ((s[:19], "%Y-%m-%d %H:%M:%S"), (s[:16], "%Y-%m-%d %H:%M")):
            try:
                dt = datetime.strptime(chunk, fmt)
                return (dt.hour, dt.minute)
            except ValueError:
                pass
        return (99, 99)

    for row in items:
        try:
            d = _parse_date(row.get("appointment_date", row.get("date")))
        except (TypeError, ValueError):
            continue
        key = (d.year, d.month, d.day)
        buckets.setdefault(key, []).append(row)
    for appts in buckets.values():
        appts.sort(key=sort_key)
    return buckets


def _appointment_counts_by_client(items: list[dict[str, Any]]) -> dict[str, int]:
    """Total de citas por cliente en todo el histórico cargado (lista API)."""
    counts: dict[str, int] = {}
    for row in items:
        k = _client_history_key(row)
        counts[k] = counts.get(k, 0) + 1
    return counts



def _render_main_calendar(
    buckets: dict[tuple[int, int, int], list[dict[str, Any]]],
    counts_by_client: dict[str, int],
    *,
    team_layout: bool = False,
) -> None:
    """Rejilla mensual en fragment (`calendar_main_month`)."""
    _render_main_calendar_impl(
        buckets,
        counts_by_client,
        team_layout=team_layout,
        clear_calendar_dialog_focus=_clear_calendar_dialog_focus,
        panel_is_technician_role=_panel_is_technician_role,
    )


def _fetch_appointments() -> None:
    qid = _appointments_query_assigned_user_id()
    ok, code, data = api_client.get_appointments(assigned_panel_user_id=qid)
    if ok and isinstance(data, list):
        data = _filter_appointments_for_session_role(data)
        st.session_state["_ap_list"] = data
        st.session_state["_ap_err"] = None
        _purge_appointment_payment_caches()
        _purge_appointment_receipt_caches()
    else:
        st.session_state["_ap_list"] = []
        st.session_state["_ap_err"] = f"HTTP {code}: {format_http_error_detail(data)}"





def _render_cita_row_actions(r: Dict[str, Any], *, show_firma: bool = True) -> None:
    """
    Menú de acciones por fila. `show_firma=False` omite la firma en vista administrativa (p. ej. Reporte).

    Tatuadores y perforadores solo ven acciones de **firma profesional** (sin flujo de cliente ni encuesta).
    """
    appt_id = int(r.get("id", 0) or 0)
    status = str(r.get("status") or "Agendada")
    firmar_disabled = _firmar_contrato_disabled(r)
    repro_disabled = reprogram_disabled_for_row(r)
    montos_disabled = appt_id <= 0 or status not in {"Agendada", "Reprogramada"}
    anular_disabled = appt_id <= 0 or status in {"Cancelada", "Finalizada"}
    firma_lbl = _firmar_contrato_button_label(r)

    if _panel_is_technician_role():
        pop = getattr(st, "popover", None)
        if pop:
            with pop("Firma profesional", use_container_width=True):
                if appt_id > 0:
                    st.caption(f"Cita #{appt_id}")
                if st.button(
                    firma_lbl,
                    disabled=firmar_disabled,
                    use_container_width=True,
                    key=f"pop_firmar_{appt_id}",
                ):
                    _open_firma_contrato_nav(r, appt_id)
            return
        if st.button(
            firma_lbl,
            disabled=firmar_disabled,
            use_container_width=True,
            key=f"fb_tech_only_{appt_id}",
        ):
            _open_firma_contrato_nav(r, appt_id)
        return

    pop = getattr(st, "popover", None)
    if pop:
        with pop("Acciones", use_container_width=True):
            if appt_id > 0:
                st.caption(f"Cita #{appt_id}")
                st.caption(f"Artista: **{_assigned_artist_display_name(r)}**")
            if show_firma:
                if st.button(
                    "Firmar contrato",
                    disabled=firmar_disabled,
                    use_container_width=True,
                    key=f"pop_firmar_{appt_id}",
                ):
                    _open_firma_contrato_nav(r, appt_id)
            if st.button(
                "Reprogramar cita",
                disabled=repro_disabled,
                use_container_width=True,
                key=f"pop_repr_{appt_id}",
                help="Solo **Agendada** o **Reprogramada** y sin contrato firmado. Tras firmar, la cita queda finalizada y no se reprograma.",
            ):
                st.session_state["_ap_reprogram_item"] = r
                st.rerun()
            if st.button(
                "Montos",
                disabled=montos_disabled,
                use_container_width=True,
                key=f"pop_fin_{appt_id}",
            ):
                st.session_state["_ap_fin_item"] = r
                st.rerun()
            rec_dis = appt_id <= 0
            if st.button(
                "Recibos (PDF)",
                disabled=rec_dis,
                use_container_width=True,
                key=f"pop_rec_{appt_id}",
                help="Descargar comprobantes emitidos al agendar o al abonar",
            ):
                st.session_state["_ap_receipts_item"] = r
                st.rerun()
            if st.button(
                "Anular",
                disabled=anular_disabled,
                use_container_width=True,
                key=f"pop_can_{appt_id}",
            ):
                st.session_state["_ap_cancel_item"] = r
                st.rerun()
        return

    if appt_id > 0:
        st.caption(f"Cita #{appt_id}")
    st.caption(f"Artista: **{_assigned_artist_display_name(r)}**")
    if show_firma:
        ln1, ln2 = st.columns(2)
        with ln1:
            if st.button(
                "Firmar",
                disabled=firmar_disabled,
                use_container_width=True,
                key=f"fb_compact_{appt_id}",
            ):
                _open_firma_contrato_nav(r, appt_id)
        with ln2:
            if st.button("Mover", disabled=repro_disabled, use_container_width=True, key=f"fb_repr_{appt_id}"):
                st.session_state["_ap_reprogram_item"] = r
                st.rerun()
    else:
        if st.button("Mover", disabled=repro_disabled, use_container_width=True, key=f"fb_repr_{appt_id}"):
            st.session_state["_ap_reprogram_item"] = r
            st.rerun()
    bn1, bn2, bn3 = st.columns(3)
    with bn1:
        if st.button("Montos", disabled=montos_disabled, use_container_width=True, key=f"fb_fin_{appt_id}"):
            st.session_state["_ap_fin_item"] = r
            st.rerun()
    with bn2:
        rec_key_dis = appt_id <= 0
        if st.button(
            "Recibos",
            disabled=rec_key_dis,
            use_container_width=True,
            key=f"fb_rec_{appt_id}",
            help="PDF si hubo abono al agendar y por cada abono adicional",
        ):
            st.session_state["_ap_receipts_item"] = r
            st.rerun()
    with bn3:
        if st.button("Anular", disabled=anular_disabled, use_container_width=True, key=f"fb_can_{appt_id}"):
            st.session_state["_ap_cancel_item"] = r
            st.rerun()


def _apply_appointment_filters(
    items: list[dict[str, Any]],
    *,
    use_date_range: bool = True,
    name_key: str = "_ap_f_name",
    service_key: str = "_ap_f_service",
    status_key: str = "_ap_f_status",
    store_key: str = "_ap_cal_f_store_id",
) -> list[dict[str, Any]]:
    """Lee filtros desde `session_state` y delega en `filter_appointment_rows` (lógica pura)."""
    try:
        store_id = int(st.session_state.get(store_key) or 0)
    except (TypeError, ValueError):
        store_id = 0
    return filter_appointment_rows(
        items,
        name_substr=str(st.session_state.get(name_key) or ""),
        service=str(st.session_state.get(service_key) or "Todos"),
        status=str(st.session_state.get(status_key) or "Todos"),
        store_id=store_id,
        from_date=st.session_state.get("_ap_f_from") if use_date_range else None,
        to_date=st.session_state.get("_ap_f_to") if use_date_range else None,
    )



def _inject_citas_shared_styles() -> None:
    """CSS consolidado desde `streamlit_app/styles/` (arquitectura del tab Citas)."""
    inject_via_streamlit_lazy()


def _init_appt_tab_session_state() -> None:
    if "_ap_page" not in st.session_state:
        st.session_state["_ap_page"] = 0
    if "_ap_limit" not in st.session_state:
        st.session_state["_ap_limit"] = 10
    if "_ap_reload" not in st.session_state:
        st.session_state["_ap_reload"] = True
    if "_ap_f_name" not in st.session_state:
        st.session_state["_ap_f_name"] = ""
    if "_ap_f_service" not in st.session_state:
        st.session_state["_ap_f_service"] = "Todos"
    if "_ap_f_status" not in st.session_state:
        st.session_state["_ap_f_status"] = "Todos"
    if "_ap_f_from" not in st.session_state:
        st.session_state["_ap_f_from"] = None
    if "_ap_f_to" not in st.session_state:
        st.session_state["_ap_f_to"] = None
    if "_ap_cal_f_store_id" not in st.session_state:
        st.session_state["_ap_cal_f_store_id"] = 0
    if "_ap_cal_f_service" not in st.session_state:
        st.session_state["_ap_cal_f_service"] = "Todos"
    if "_ap_cal_f_status" not in st.session_state:
        st.session_state["_ap_cal_f_status"] = "Todos"
    if "_ap_search_field" not in st.session_state:
        st.session_state["_ap_search_field"] = "name"
    if "_ap_search_q" not in st.session_state:
        st.session_state["_ap_search_q"] = ""
    if "_ap_search_page" not in st.session_state:
        st.session_state["_ap_search_page"] = 0


def warm_session_after_login(allowed_module_keys: frozenset[str]) -> None:
    """Precarga agenda en sesión tras iniciar sesión (usar dentro del spinner en main)."""
    if "citas" not in allowed_module_keys and "reporte" not in allowed_module_keys:
        return
    _init_appt_tab_session_state()
    st.session_state["_ap_reload"] = True
    _sync_appointments_from_api()


def _invoke_citas_tab_dialogs(
    by_day: dict[tuple[int, int, int], list[dict[str, Any]]],
    hist_counts: dict[str, int],
) -> None:
    """Abre diálogos si hay foco de calendario o acciones pendientes (p. ej. tras ?cal_appt_id=)."""
    _technician_clear_disallowed_dialog_states()
    if (
        st.session_state.get("_ap_fin_item")
        or st.session_state.get("_ap_reprogram_item")
        or st.session_state.get("_ap_receipts_item")
    ):
        _clear_calendar_dialog_focus()
    if st.session_state.get("_ap_reprogram_item"):
        dialog_reprogramar_cita()
    if st.session_state.get("_ap_fin_item"):
        dialog_ajustar_montos()
    if st.session_state.get("_ap_cancel_item"):
        dialog_cancelar_cita()
    if st.session_state.get("_ap_receipts_item"):
        dialog_recibos_cita()
    cal_focus_id = st.session_state.get("_cal_focus_appt_id")
    cal_overflow = st.session_state.get("_cal_overflow_day")
    if cal_focus_id or cal_overflow:
        # No limpiar deps en finally: el cuerpo del @st.dialog corre en el mismo rerun y necesita _deps().
        set_calendar_focus_session_deps(
            CalendarFocusDeps(
                panel_is_technician_role=_panel_is_technician_role,
                clear_calendar_dialog_focus=_clear_calendar_dialog_focus,
                open_firma_contrato_nav=_open_firma_contrato_nav,
                firmar_contrato_disabled=_firmar_contrato_disabled,
                firmar_contrato_button_label=_firmar_contrato_button_label,
                reprogram_disabled_for_row=reprogram_disabled_for_row,
                appointment_detail_plain_body=_appointment_detail_plain_body,
                split_design_obs_plain=_split_design_obs_plain,
                rebuild_detail_for_patch=_rebuild_detail_for_patch,
                ensure_assignable_staff=ensure_assignable_staff,
                work_kind_to_assignee_role=work_kind_to_assignee_role,
                work_kind_infer_from_existing_row=work_kind_infer_from_existing_row,
                find_appointment_row_by_id=_find_appointment_row_by_id,
                parse_date=_parse_date,
                get_appointment_payments_cached=_get_appointment_payments_cached,
                purge_appointment_payment_caches=_purge_appointment_payment_caches,
                queue_appointment_action_success=_queue_appointment_action_success,
                api_error=format_http_error_detail,
                receipts_cache_prefix=str(KEY_RECEIPTS_LIST_PFX),
                fin_payments_cache_prefix=str(KEY_FIN_PAYMENTS_PFX),
            )
        )
        if cal_focus_id:
            dialog_calendar_single_appointment(by_day, hist_counts)
        else:
            dialog_calendar_day_appointments(by_day, hist_counts)
    else:
        clear_calendar_focus_session_deps()
    if st.session_state.get("_ap_search_dlg"):
        dialog_buscar_cita(
            query_assigned_user_id=_appointments_query_assigned_user_id,
            filter_for_role=_filter_appointments_for_session_role,
        )
    if st.session_state.get("_ap_dlg") == "create":
        dialog_agendar_cita()


def _sync_appointments_from_api() -> None:
    """
    GET /appointments solo si hubo cambios, cambio de filtro o primera carga.
    Precalcula hist_counts y svc_values cuando se refrescan datos.
    """
    qid = _appointments_query_assigned_user_id()
    prev_qid = st.session_state.get("_ap_last_fetch_qid")
    fetch_needed = (
        st.session_state.get("_ap_reload", True)
        or prev_qid != qid
        or st.session_state.pop("_ap_refresh_after_contract", False)
    )
    if not fetch_needed:
        items_miss = st.session_state.get("_ap_list") or []
        if items_miss:
            if "_ap_hist_counts" not in st.session_state:
                st.session_state["_ap_hist_counts"] = _appointment_counts_by_client(items_miss)
            if "_ap_svc_values" not in st.session_state:
                st.session_state["_ap_svc_values"] = sorted(
                    {
                        str(i.get("service_type", i.get("service", "")) or "").strip()
                        for i in items_miss
                        if str(i.get("service_type", i.get("service", "")) or "").strip()
                    }
                )
        return

    with st.spinner("Actualizando citas…"):
        _fetch_appointments()

    items_post: list[Any] = st.session_state.get("_ap_list") or []
    st.session_state["_ap_hist_counts"] = _appointment_counts_by_client(items_post)
    st.session_state["_ap_svc_values"] = sorted(
        {
            str(i.get("service_type", i.get("service", "")) or "").strip()
            for i in items_post
            if str(i.get("service_type", i.get("service", "")) or "").strip()
        }
    )

    for k in [k for k in st.session_state if isinstance(k, str) and k.startswith("_ap_xlsx_")]:
        st.session_state.pop(k, None)

    st.session_state["_ap_reload"] = False
    st.session_state["_ap_last_fetch_qid"] = qid


def render_reporte_citas_tab() -> None:
    """Pestaña Reporte: finanzas y encuestas en sub-secciones; mismos filtros de citas para finanzas."""
    _init_appt_tab_session_state()
    _inject_citas_shared_styles()
    _sync_appointments_from_api()

    _technician_clear_disallowed_dialog_states()

    _render_appointments_fetch_error_toast()
    _render_appointment_action_feedback()
    toast_financial_save_error_if_any()

    items = list(st.session_state.get("_ap_list") or [])
    svc_values = list(st.session_state.get("_ap_svc_values") or [])
    status_values = ["Agendada", "Reprogramada", "Finalizada", "Cancelada"]

    if st.session_state.get("_ap_reprogram_item"):
        dialog_reprogramar_cita()
    if st.session_state.get("_ap_fin_item"):
        dialog_ajustar_montos()
    if st.session_state.get("_ap_cancel_item"):
        dialog_cancelar_cita()
    if st.session_state.get("_ap_receipts_item"):
        dialog_recibos_cita()

    st.markdown('<div class="rep-tab-root" aria-hidden="true"></div>', unsafe_allow_html=True)
    st.markdown("##### Gestión reportes")
    # st.tabs ejecuta cada pestaña en cada rerun; el radio solo dibuja una rama.
    rep_sec = st.radio(
        "Sección",
        ["Finanzas — citas", "Encuestas — satisfacción"],
        horizontal=True,
        key="rep_subsection",
    )
    if rep_sec.startswith("Finanzas"):
        render_reporte_financiero_citas_body(
            items,
            svc_values,
            status_values,
            client_history_key=_client_history_key,
        )
    else:
        st.markdown("##### Resumen por pregunta")
        with st.spinner("Cargando estadísticas de encuesta…"):
            render_survey_question_stats_report()


def render_citas_tab() -> None:
    """Calendario, agendar y diálogo de citas del día; datos financieros y tabla en **Reporte**."""
    _init_appt_tab_session_state()
    _consume_cal_nav_component_result()
    _inject_citas_shared_styles()
    _sync_appointments_from_api()

    _render_appointments_fetch_error_toast()
    _render_appointment_action_feedback()
    toast_financial_save_error_if_any()

    items = list(st.session_state.get("_ap_list") or [])
    svc_values = list(st.session_state.get("_ap_svc_values") or [])
    status_values = ["Agendada", "Reprogramada", "Finalizada", "Cancelada"]

    _render_citas_color_legend()

    _, filt_head_m, filt_head_r = st.columns([3.4, 1.15, 1.35])
    with filt_head_m:
        st.write("")
        st.write("")
        if st.button(
            "Buscar cita",
            use_container_width=True,
            icon=":material/search:",
            key="btn_buscar_cita_cal",
        ):
            st.session_state["_ap_search_dlg"] = True
            st.session_state.pop("_ap_search_result", None)
            st.session_state.pop("_ap_search_err", None)
    with filt_head_r:
        _cex_disabled = _panel_is_technician_role()
        st.write("")
        st.write("")
        if st.button(
            "Cita express",
            type="primary",
            use_container_width=True,
            disabled=_cex_disabled,
            key="btn_cita_express_cal_header",
            help=(
                "Piercing: agenda con abono completo, alta de cliente, encuesta de piercing y firma del contrato."
                if not _cex_disabled
                else "Los tatuadores y perforadores no pueden iniciar este flujo desde aquí."
            ),
        ):
            open_contract_express_piercing()
    _render_calendar_filters_row(svc_values=svc_values, status_values=status_values)

    vista_compact = "Mes — compacta"
    vista_team = "Mes — por equipo"
    vista_week = "Semana"
    if st.session_state.get("_ap_cal_vista") == "Semana (rejilla)":
        st.session_state["_ap_cal_vista"] = vista_week
    if st.session_state.get("_ap_cal_period") == "Semana (rejilla)":
        st.session_state["_ap_cal_period"] = "Semana"

    fid = int(st.session_state.get("_ap_filter_artist_id") or 0)
    may_all = _may_see_all_appointments()
    can_team = may_all and fid == 0
    vista_options: list[str] = [vista_compact] + ([vista_team] if can_team else []) + [vista_week]

    period_key = "_ap_cal_period"
    layout_key = "_ap_cal_layout"
    if period_key not in st.session_state:
        st.session_state[period_key] = "Mes"

    if "_ap_cal_vista" not in st.session_state:
        pk = str(st.session_state.get(period_key) or "Mes")
        lk = str(st.session_state.get(layout_key) or "Compacta")
        if pk in ("Semana (rejilla)", "Semana"):
            st.session_state["_ap_cal_vista"] = vista_week
        elif lk == "Por equipo" and can_team:
            st.session_state["_ap_cal_vista"] = vista_team
        else:
            st.session_state["_ap_cal_vista"] = vista_compact

    vista = str(st.session_state.get("_ap_cal_vista") or vista_compact)
    if vista == vista_team and not can_team:
        vista = vista_compact
        st.session_state["_ap_cal_vista"] = vista_compact
    if vista not in vista_options:
        vista = vista_compact
        st.session_state["_ap_cal_vista"] = vista_compact

    prev_vista = st.session_state.get("__ap_cal_vista_prev")
    if vista == vista_week and prev_vista != vista_week:
        _clear_calendar_dialog_focus()
        _sync_week_monday_for_agenda_context()

    st.radio(
        "Vista calendario",
        vista_options,
        horizontal=True,
        key="_ap_cal_vista",
    )

    vista = str(st.session_state.get("_ap_cal_vista") or vista_compact)
    if vista == vista_team and not can_team:
        vista = vista_compact
        st.session_state["_ap_cal_vista"] = vista_compact
    if vista not in vista_options:
        vista = vista_compact
        st.session_state["_ap_cal_vista"] = vista_compact

    st.session_state["__ap_cal_vista_prev"] = vista

    team_layout = False
    if vista == vista_week:
        period_sel = "Semana"
    elif vista == vista_team:
        period_sel = "Mes"
        team_layout = True
        st.session_state[layout_key] = "Por equipo"
        st.session_state[period_key] = "Mes"
    else:
        period_sel = "Mes"
        st.session_state[layout_key] = "Compacta"
        st.session_state[period_key] = "Mes"

    cal_filtered = _apply_appointment_filters(
        items,
        use_date_range=False,
        name_key="_ap_f_name",
        service_key="_ap_cal_f_service",
        status_key="_ap_cal_f_status",
        store_key="_ap_cal_f_store_id",
    )
    hc_raw = st.session_state.get("_ap_hist_counts")
    hist_counts: dict[str, int] = dict(hc_raw) if isinstance(hc_raw, dict) else {}
    if not hist_counts and items:
        hist_counts = _appointment_counts_by_client(items)
    by_day = _appointments_by_day_sorted(cal_filtered)

    _invoke_citas_tab_dialogs(by_day, hist_counts)

    if period_sel == "Semana":
        render_week_schedule_grid(
            by_day,
            hist_counts,
            clear_calendar_dialog_focus=_clear_calendar_dialog_focus,
            panel_is_technician_role=_panel_is_technician_role,
            pop_booking_document_session=_pop_booking_document_session,
        )
    else:
        _render_main_calendar(by_day, hist_counts, team_layout=team_layout)

    inject_calendar_query_nav_bridge()
