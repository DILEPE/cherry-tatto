"""Borrador alternativo de extracción fase 2 (detalle + reporte + encuestas).

No ejecutar en producción: termina con SystemExit(1). Referencia de rangos y reemplazos;
ver scripts/README-citas-tab-refactor.md y preferir _extract_modules.py + poda manual.
"""

from pathlib import Path

root = Path(__file__).resolve().parent.parent
p = root / "streamlit_app" / "citas_tab.py"
lines = lines_list = p.read_text(encoding="utf-8").splitlines(keepends=True)


def ins(a: int, b: int) -> str:
    return "".join(lines_list[a - 1 : b])


# --- citas_detail_dialogs.py ---
header_detail = '''"""Di\\u00e1logos de cita desde fila/lista: reprogramar, montos, anular, recibos PDF."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

import streamlit as st

from app.domain.appointment_money import coerce_float, format_cop
from app.domain.contract_kinds import appointment_to_contract_kind
from streamlit_app import api_client
from streamlit_app.appointment_agenda_slots import duration_slots_for_existing_appointment
from streamlit_app.appointment_dates import (
    combine_appointment_datetime,
    format_api_datetime_compact_es,
)
from streamlit_app.appointment_slots import (
    available_start_slots,
    busy_slot_indices_for_day,
    parse_existing_appointment_slot,
    time_slot_options,
)
from streamlit_app.citas_agendar_dialog import queue_appointment_action_success
from streamlit_app.citas_row_policy import reprogram_disabled_for_row
from streamlit_app.citas_schedule_queries import (
    appointments_for_artist_schedule,
    appointments_same_day_schedule_kind,
)
from streamlit_app.appointment_staff_labels import assigned_artist_display_name
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

toast = ins(218, 226)

shift_block = """def _shift_years(base: date, years: int) -> date:\n""" + ins(771, 781)

body_detail = (
    toast
    + "\n"
    + shift_block
    + "\n"
    + ins(1523, 1527)
    + ins(1661, 1665)
    + ins(1528, 1658)
    + "\n\n"
    + ins(1666, 1726)
    + "\n\n"
    + ins(1728, 1888)
    + "\n\n"
    + ins(1891, 1968)
)

subs_detail = [
    ("def _cleanup_reprogram_dialog_state", "def cleanup_reprogram_dialog_state"),
    ("_cleanup_reprogram_dialog_state()", "cleanup_reprogram_dialog_state()"),
    ("def _label_cancel_abono", "def label_cancel_abono"),
    ("format_func=_label_cancel_abono", "format_func=label_cancel_abono"),
    ("def _dialog_reprogramar_cita", "def dialog_reprogramar_cita"),
    ("def _dialog_cancelar_cita", "def dialog_cancelar_cita"),
    ("def _dialog_ajustar_montos", "def dialog_ajustar_montos"),
    ("def _dialog_recibos_cita", "def dialog_recibos_cita"),
    ("_reprogram_disabled_for_row", "reprogram_disabled_for_row"),
    ("_toast_financial_save_error_if_any", "toast_financial_save_error_if_any"),
    ("_AP_TOAST_FIN_SAVE_ERR_KEY", "KEY_TOAST_FIN_SAVE_ERR"),
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
]

for a, b in subs_detail:
    body_detail = body_detail.replace(a, b)

footer_detail = """

__all__ = [
    "cleanup_reprogram_dialog_state",
    "dialog_ajustar_montos",
    "dialog_cancelar_cita",
    "dialog_reprogramar_cita",
    "dialog_recibos_cita",
]
"""

(root / "streamlit_app" / "citas_detail_dialogs.py").write_text(header_detail + body_detail + footer_detail, encoding="utf-8")


# --- citas_row_policy.py ---
policy = '''"""Reglas de estado de fila Citas sin Streamlit pesado."""

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
(root / "streamlit_app" / "citas_row_policy.py").write_text(policy, encoding="utf-8")

# --- reporte_finanzas_citas.py ---
header_rf = '''"""Reporte financiero Citas (filtros, m\\xe9tricas, Excel y tabla paginada)."""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional

import streamlit as st

from app.domain.appointment_money import (
    appointment_financial_totals,
    calendar_month_compact_label,
    coerce_float,
    customer_credit_from_row,
    format_cop,
)
from streamlit_app import report_charts
from streamlit_app.appointment_dates import appointment_row_date as parse_date_fallback
from streamlit_app.appointment_filters import filter_appointment_rows
from streamlit_app.appointment_staff_labels import assigned_artist_display_name as artist_display_name
from streamlit_app.citas_financial_export import citas_filtered_to_excel_bytes
from streamlit_app.components.pills import (
    customer_name_pill_html,
    row_is_priority,
    status_pill_html,
)
from streamlit_app.components.service_flags import service_type_flag_html


def appointment_counts_by_client(items: list[dict[str, Any]], client_history_key_fn) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in items:
        k = client_history_key_fn(row)
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


def apply_report_appointment_filters(
    items: list[dict[str, Any]],
    *,
    use_date_range: bool = True,
    name_key: str = "_ap_f_name",
    service_key: str = "_ap_f_service",
    status_key: str = "_ap_f_status",
) -> list[dict[str, Any]]:
    return filter_appointment_rows(
        items,
        name_substr=str(st.session_state.get(name_key) or ""),
        service=str(st.session_state.get(service_key) or "Todos"),
        status=str(st.session_state.get(status_key) or "Todos"),
        from_date=st.session_state.get("_ap_f_from") if use_date_range else None,
        to_date=st.session_state.get("_ap_f_to") if use_date_range else None,
    )


'''

body_rf_mid = (
    ins(2003, 2026).replace("_financial_row_values", "appointment_financial_totals").replace("_render_vertical", " ")
)

# Paste procedure chart + excel + render body explicitly from known ranges
procedure = ins(2003, 2026)
procedure = procedure.replace("_financial_row_values", "appointment_financial_totals")
procedure = procedure.replace("_customer_credit_value(row)", "customer_credit_from_row(row)")
procedure = procedure.replace("report_charts.render_vertical_bars", "report_charts.render_vertical_bars")

finger = ins(2210, 2237).replace("_citas_filtered_to_excel_bytes", "citas_filtered_to_excel_bytes")
render_body = ins(2239, 2361)
render_body = render_body.replace("_apply_appointment_filters", "apply_report_appointment_filters")
render_body = render_body.replace("_appointment_counts_by_client", "appointment_counts_by_client").replace("(items)", "(items, customer_name_pill_html.__wrapped__)")


print("ABORT tuning report body manually")
raise SystemExit(1)
