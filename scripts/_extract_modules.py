"""Extrae citas_row_policy, citas_detail_dialogs, survey y reporte_finanzas desde citas_tab.

Ver scripts/README-citas-tab-refactor.md. Sobrescribe módulos en streamlit_app/; revisar diff y firma del reporte.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
p = ROOT / "streamlit_app" / "citas_tab.py"
L = p.read_text(encoding="utf-8").splitlines(keepends=True)


def ln(a: int, b: int) -> str:
    return "".join(L[a - 1 : b])


POLICY_TXT = '''"""Reglas por fila Citas sin Streamlit pesado."""

from __future__ import annotations

from typing import Any, Dict


def reprogram_disabled_for_row(r: Dict[str, Any]) -> bool:
    """Reprogramar solo en Agendada/Reprogramada, sin contrato firmado y no cancelada."""
    appt_id = int(r.get("id", 0) or 0)
    status = str(r.get("status") or "Agendada")
    if appt_id <= 0 or status == "Cancelada":
        return True
    if status not in {"Agendada", "Reprogramada"}:
        return True
    if bool(r.get("has_signed_contract")):
        return True
    return False


__all__ = ["reprogram_disabled_for_row"]
'''
(ROOT / "streamlit_app" / "citas_row_policy.py").write_text(POLICY_TXT, encoding="utf-8")

# citas_detail_dialogs
HDR = '''"""Dialogs cita desde fila: repr., montos, anular, recibos."""

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


'''
body = (
    ln(218, 226).replace("_AP_TOAST_FIN_SAVE_ERR_KEY", "KEY_TOAST_FIN_SAVE_ERR")
    + ln(770, 781)
    + ln(1523, 1527)
    + ln(1529, 1658)
    + ln(1661, 1726)
    + ln(1728, 1888)
    + ln(1891, 1968)
)
for o, n in [
    ("def _cleanup_reprogram_dialog_state", "def cleanup_reprogram_dialog_state"),
    ("_cleanup_reprogram_dialog_state()", "cleanup_reprogram_dialog_state()"),
    ("def _label_cancel_abono", "def label_cancel_abono"),
    ("format_func=_label_cancel_abono", "format_func=label_cancel_abono"),
    ("def _dialog_reprogramar_cita", "def dialog_reprogramar_cita"),
    ("def _dialog_cancelar_cita", "def dialog_cancelar_cita"),
    ("def _dialog_ajustar_montos", "def dialog_ajustar_montos"),
    ("def _dialog_recibos_cita", "def dialog_recibos_cita"),
    ("_toast_financial_save_error_if_any", "toast_financial_save_error_if_any"),
    ("_reprogram_disabled_for_row", "reprogram_disabled_for_row"),
    ("_assigned_artist_display_name", "assigned_artist_display_name"),
    ("_duration_slots_for_existing_appointment", "duration_slots_for_existing_appointment"),
    ("_time_slot_options()", "time_slot_options()"),
    ("_busy_slot_indices_for_day", "busy_slot_indices_for_day"),
    ("_available_start_slots", "available_start_slots"),
    ("_combine_appointment_datetime", "combine_appointment_datetime"),
    ("_appointments_for_artist_schedule", "appointments_for_artist_schedule"),
    ("_appointments_same_day_schedule_kind", "appointments_same_day_schedule_kind"),
    ("_parse_existing_slot", "parse_existing_appointment_slot"),
    ("_format_dt_for_user_message", "format_api_datetime_compact_es"),
    ("_queue_appointment_action_success", "queue_appointment_action_success"),
    ("_format_cop(", "format_cop("),
    ("_api_error(", "format_http_error_detail("),
    ("_to_float(", "coerce_float("),
    ("_get_appointment_payments_cached", "get_appointment_payments_cached"),
    ("_purge_appointment_receipt_caches", "purge_appointment_receipt_caches"),
    ("_AP_RECEIPTS_CACHE_PREFIX", "KEY_RECEIPTS_LIST_PFX"),
    ("_AP_RECEIPT_PDF_PFX", "KEY_RECEIPT_PDF_PFX"),
    ("_AP_FIN_PAYMENTS_CACHE_PREFIX", "KEY_FIN_PAYMENTS_PFX"),
]:
    body = body.replace(o, n)
(ROOT / "streamlit_app" / "citas_detail_dialogs.py").write_text(
    HDR + body + "\n__all__ = ['cleanup_reprogram_dialog_state','dialog_ajustar_montos','dialog_cancelar_cita','dialog_reprogramar_cita','dialog_recibos_cita']\n",
    encoding="utf-8",
)

# survey
HDRS = """\"\"\"Encuesta: resumen plot por pregunta.\"\"\"
from __future__ import annotations
import unicodedata
from typing import Any, Optional
import streamlit as st
from app.domain.contract_kinds import SCOPE_LABEL_ES
from app.domain.survey_question_helpers import question_type_label_es, question_type_supports_distribution_chart
from streamlit_app import report_charts
from streamlit_app.cached_public_api import get_survey_question_stats_summary_cached
from streamlit_app.http_error_detail import format_http_error_detail


"""
survey = ln(2028, 2207)
for o, n in [
    ("def _truncate_survey_chart_label", "def truncate_survey_chart_label"),
    ("_truncate_survey_chart_label(", "truncate_survey_chart_label("),
    ("def _survey_pie_chart_from_counts", "def survey_pie_chart_from_counts"),
    ("_survey_pie_chart_from_counts(", "survey_pie_chart_from_counts("),
    ("def _normalize_survey_label_ascii_lower", "def normalize_survey_label_ascii_lower"),
    ("_normalize_survey_label_ascii_lower", "normalize_survey_label_ascii_lower"),
    ("def _survey_question_is_procedure_value_question", "def survey_question_is_procedure_value_question"),
    ("_survey_question_is_procedure_value_question", "survey_question_is_procedure_value_question"),
    ("def _pairs_from_number_breakdown", "def pairs_from_number_breakdown"),
    ("_pairs_from_number_breakdown", "pairs_from_number_breakdown"),
    ("def _survey_number_bar_chart_2d", "def survey_number_bar_chart_2d"),
    ("_survey_number_bar_chart_2d(", "survey_number_bar_chart_2d("),
    ("def _render_survey_question_stats_report", "def render_survey_question_stats_report"),
    ("_api_error(", "format_http_error_detail("),
]:
    survey = survey.replace(o, n)
(ROOT / "streamlit_app" / "survey_question_stats_report.py").write_text(HDRS + survey + "\n__all__=['render_survey_question_stats_report']\n", encoding="utf-8")

# finance helpers + slices
HDRF = """\"\"\"Reporte finanzas citas.\"\"\"
from __future__ import annotations
import hashlib
import json
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Callable

import streamlit as st

from app.domain.appointment_money import (
    appointment_financial_totals,
    customer_credit_from_row,
    format_cop,
)
from streamlit_app import report_charts
from streamlit_app.appointment_filters import filter_appointment_rows
from streamlit_app.appointment_staff_labels import assigned_artist_display_name
from streamlit_app.citas_financial_export import citas_filtered_to_excel_bytes
from streamlit_app.components.pills import customer_name_pill_html, status_pill_html


def appointment_counts_by_client(items: list[dict[str, Any]], key_fn: Callable[..., str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in items:
        k = key_fn(row)
        counts[k] = counts.get(k, 0) + 1
    return counts


def format_appt_when(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, datetime):
        return val.strftime("%d/%m/%Y %H:%M")
    if isinstance(val, date):
        return val.strftime("%d/%m/%Y")
    s = str(val).strip().replace("T", " ")
    if not s:
        return ""
    for c in (s, s[:19], s[:10]):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(c, fmt)
                if fmt == "%Y-%m-%d":
                    return dt.strftime("%d/%m/%Y")
                return dt.strftime("%d/%m/%Y %H:%M")
            except ValueError:
                pass
    return s[:16]


def apply_report_filters(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return filter_appointment_rows(
        items,
        name_substr=str(st.session_state.get("_ap_f_name") or ""),
        service=str(st.session_state.get("_ap_f_service") or "Todos"),
        status=str(st.session_state.get("_ap_f_status") or "Todos"),
        from_date=st.session_state.get("_ap_f_from"),
        to_date=st.session_state.get("_ap_f_to"),
    )


"""

proc = ln(2003, 2026)
for o, n in [
    ("def _render_procedure_value_bar_chart", "def render_procedure_value_bar_chart"),
    ("_financial_row_values", "appointment_financial_totals"),
    ("_customer_credit_value", "customer_credit_from_row"),
]:
    proc = proc.replace(o, n)

excel = ln(2210, 2237).replace("_citas_filtered_to_excel_bytes", "citas_filtered_to_excel_bytes")
for o, n in [
    ("def _excel_fingerprint", "def excel_fingerprint"),
    ("def _get_excel_cached", "def get_excel_cached"),
    ("_excel_fingerprint", "excel_fingerprint"),
]:
    excel = excel.replace(o, n)

render = ln(2239, 2361).replace(
    "def _render_reporte_financiero_citas_body(",
    "def render_reporte_financiero_citas_body(",
)
render = render.replace("_apply_appointment_filters", "apply_report_filters").replace(
    "_appointment_counts_by_client(items)",
    "appointment_counts_by_client(items, client_history_key)",
)
render = render.replace("_financial_row_values", "appointment_financial_totals")
render = render.replace("_customer_credit_value", "customer_credit_from_row")
render = render.replace("_format_cop(", "format_cop(")
render = render.replace("_get_excel_cached", "get_excel_cached").replace("_excel_fingerprint", "excel_fingerprint")
render = render.replace("_assigned_artist_display_name", "assigned_artist_display_name")
render = render.replace("_customer_name_pill_html", "customer_name_pill_html").replace("_status_pill_html", "status_pill_html")
render = render.replace("_format_appt_when", "format_appt_when")

import re as _re

render = render.replace("_render_procedure_value_bar_chart", "render_procedure_value_bar_chart")
render = re.sub(
    r"def render_reporte_financiero_citas_body\(\n\s+items:.+?\n\s+status_values: list\[str\],\n\) -> None:",
    """def render_reporte_financiero_citas_body(
    items: list[dict[str, Any]],
    svc_values: list[str],
    status_values: list[str],
    *,
    client_history_key: Callable[..., str],
    render_row_actions: Callable[..., None],
) -> None:""",
    render,
    count=1,
    flags=re.DOTALL,
)
render = render.replace("_render_cita_row_actions(", "render_row_actions(")


(ROOT / "streamlit_app" / "reporte_finanzas_citas.py").write_text(
    HDRF + proc + "\n\n" + excel + "\n\n" + render
    + "\n__all__=['render_procedure_value_bar_chart','render_reporte_financiero_citas_body']\n",
    encoding="utf-8",
)

print("Written detail, survey, finance modules (review finance signature manually)")
