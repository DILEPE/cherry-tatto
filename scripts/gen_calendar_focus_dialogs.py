"""Genera streamlit_app/components/calendar_focus_dialogs.py desde citas_tab.py."""
from __future__ import annotations

import re
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    citas = (root / "streamlit_app" / "citas_tab.py").read_text(encoding="utf-8")

    i_body = citas.index("def _render_calendar_focus_appointment_body")
    i_dlg = citas.index('@st.dialog("Citas del día"', i_body)
    i_pay = citas.index("\ndef _get_appointment_payments_cached(", i_dlg)

    block = citas[i_body:i_dlg]
    dialogs_chunk = citas[i_dlg:i_pay]

    body = block.replace("def _render_calendar_focus_appointment_body(", "def render_calendar_focus_appointment_body(")

    body_repls: list[tuple[str, str]] = [
        ("    aid = int", "    deps = _deps()\n    aid = int"),
        ("_panel_is_technician_role()", "deps.panel_is_technician_role()"),
        ("_row_is_priority", "row_is_priority"),
        ("_MIN_APPOINTMENT_TOTAL_COP", "deps.min_appointment_total_cop"),
        ("_MIN_BOOKING_DURATION_SLOTS", "MIN_BOOKING_DURATION_SLOTS"),
        ("_reprogram_disabled_for_row", "deps.reprogram_disabled_for_row"),
        ("_parse_existing_slot", "parse_existing_appointment_slot"),
        ("_duration_slots_from_start_last", "duration_slots_from_start_last"),
        ("_combine_appointment_datetime", "combine_appointment_datetime"),
        ("_format_appt_created_at", "format_appointment_created_at_display"),
        ("_status_pill_html", "status_pill_html"),
        ("_assigned_artist_display_name", "assigned_artist_display_name"),
        ("_ensure_assignable_staff", "deps.ensure_assignable_staff"),
        ("_work_kind_infer_from_existing_row", "deps.work_kind_infer_from_existing_row"),
        ("_work_kind_to_assignee_role", "deps.work_kind_to_assignee_role"),
        ("_get_appointment_payments_cached", "deps.get_appointment_payments_cached"),
        ("_format_cop", "format_cop"),
        ("_purge_appointment_payment_caches", "deps.purge_appointment_payment_caches"),
        ("_AP_RECEIPTS_CACHE_PREFIX", "deps.receipts_cache_prefix"),
        ("_AP_FIN_PAYMENTS_CACHE_PREFIX", "deps.fin_payments_cache_prefix"),
        ("_queue_appointment_action_success", "deps.queue_appointment_action_success"),
        ("_api_error", "deps.api_error"),
        ("_rebuild_detail_for_patch", "deps.rebuild_detail_for_patch"),
        ("_find_appointment_row_by_id", "deps.find_appointment_row_by_id"),
        ("_clear_calendar_dialog_focus()", "deps.clear_calendar_dialog_focus()"),
        ("_open_firma_contrato_nav", "deps.open_firma_contrato_nav"),
        ("_firmar_contrato_disabled", "deps.firmar_contrato_disabled"),
        ("_firmar_contrato_button_label", "deps.firmar_contrato_button_label"),
        ("_calendar_overflow_row_html(", "calendar_overflow_row_html("),
        ("_time_slot_options()", "time_slot_options()"),
        ("_duration_slots_for_existing_appointment(", "duration_slots_for_existing_appointment("),
        ("_appointment_last_start_slot(", "appointment_last_start_slot("),
        ("_appointment_detail_plain_body", "deps.appointment_detail_plain_body"),
        ("_split_design_obs_plain", "deps.split_design_obs_plain"),
    ]
    for a, b in body_repls:
        body = body.replace(a, b)

    dlg = dialogs_chunk.replace("def _dialog_calendar_day_appointments", "def dialog_calendar_day_appointments")
    dlg = dlg.replace("def _dialog_calendar_single_appointment", "def dialog_calendar_single_appointment")
    dlg = dlg.replace("_clear_calendar_dialog_focus()", "deps.clear_calendar_dialog_focus()")
    dlg = dlg.replace("_panel_is_technician_role()", "deps.panel_is_technician_role()")
    dlg = dlg.replace("_find_appointment_row_by_id(", "deps.find_appointment_row_by_id(")
    dlg = dlg.replace("_parse_date(", "deps.parse_date(")
    dlg = dlg.replace("_render_calendar_focus_appointment_body", "render_calendar_focus_appointment_body")

    dlg = re.sub(
        r"(    if not tup:\n        return)\n    y, m, d",
        r"\1\n    deps = _deps()\n    y, m, d",
        dlg,
        count=1,
    )
    dlg = re.sub(
        r"(    if aid <= 0:\n        return)\n    r = deps\.find_appointment_row_by_id",
        r"\1\n    deps = _deps()\n    r = deps.find_appointment_row_by_id",
        dlg,
        count=1,
    )

    header = '''"""Overflow del día, diálogo cita única y ficha de edición desde calendario."""

from __future__ import annotations

import html as html_mod
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Optional

import streamlit as st

from app.domain.appointment_money import format_cop
from streamlit_app import api_client
from streamlit_app.appointment_agenda_slots import MIN_BOOKING_DURATION_SLOTS, duration_slots_for_existing_appointment
from streamlit_app.appointment_dates import combine_appointment_datetime, format_appointment_created_at_display
from streamlit_app.appointment_staff_labels import assigned_artist_display_name
from streamlit_app.appointment_slots import (
    appointment_last_start_slot,
    duration_slots_from_start_last,
    parse_existing_appointment_slot,
    time_slot_options,
)
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
    min_appointment_total_cop: float
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


'''

    combined = header + "\n\n" + body.strip() + "\n\n\n" + dlg.strip() + "\n"
    out_path = root / "streamlit_app" / "components" / "calendar_focus_dialogs.py"
    out_path.write_text(combined, encoding="utf-8")
    print("Wrote", out_path)


if __name__ == "__main__":
    main()
