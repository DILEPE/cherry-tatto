"""Marcado HTML compacto para celdas y diálogos del calendario — sin `st.markdown`."""

from __future__ import annotations

import html as html_mod
from typing import Any

from app.domain.appointment_money import (
    appointment_financial_totals,
    calendar_month_compact_label,
    format_cop,
)
from streamlit_app.appointment_dates import appointment_time_hm
from streamlit_app.appointment_staff_labels import assigned_artist_display_name, assigned_staff_label
from streamlit_app.components.pills import client_pill_class, customer_name_pill_html
from streamlit_app.components.service_flags import service_type_flag_html


def calendar_cell_customer_label(full_name: str, *, long_from_len: int = 18) -> str:
    """Texto compacto en celda del calendario: nombre completo si es corto; si no, solo el primer nombre."""
    nm = (full_name or "").strip() or "—"
    if nm == "—" or len(nm) <= long_from_len:
        return nm
    parts = nm.split()
    if not parts:
        return nm[: long_from_len - 1] + "…"
    first = parts[0]
    if len(first) > long_from_len:
        return first[: long_from_len - 1] + "…"
    return first


def group_calendar_day_rows_by_assigned_staff(
    day_rows: list[dict[str, Any]],
) -> list[tuple[str, list[dict[str, Any]]]]:
    """Agrupa las citas del día por profesional asignado (orden = primera aparición temporal)."""
    order_keys: list[Any] = []
    buckets: dict[Any, list[dict[str, Any]]] = {}
    labels: dict[Any, str] = {}

    for r in day_rows:
        raw = r.get("assigned_panel_user_id")
        try:
            key = int(raw) if raw is not None and str(raw).strip() != "" else None
        except (TypeError, ValueError):
            key = None
        if key is None:
            key = "__unassigned__"
            lab = "Sin asignar"
        else:
            lab = assigned_artist_display_name(r)
        if key not in buckets:
            buckets[key] = []
            order_keys.append(key)
            labels[key] = lab
        buckets[key].append(r)

    return [(labels[k], buckets[k]) for k in order_keys]


def calendar_overflow_row_html(row: dict[str, Any], counts_by_client: dict[str, int]) -> str:
    """Línea para el diálogo de citas extra: hora + tipo de servicio + nombre + total."""
    hm = appointment_time_hm(row.get("appointment_date", row.get("date")))
    st_cl = str(row.get("status") or "").strip().lower()
    muted = " cal-overflow-row--muted" if st_cl == "cancelada" else ""
    svc_flag = service_type_flag_html(row)
    pill = customer_name_pill_html(row, counts_by_client)
    staff_s = assigned_artist_display_name(row)
    staff_el = ""
    if staff_s != "Sin asignar":
        staff_el = (
            '<span class="cal-overflow-artist-dash"> · Artista: '
            f"{html_mod.escape(staff_s)}</span>"
        )
    total_amt, _, _ = appointment_financial_totals(row)
    total_box = (
        '<span class="cal-overflow-total-wrap"><span class="cal-overflow-total-chip">'
        '<span class="cal-overflow-total-label">Total servicio</span> · '
        f'{html_mod.escape(format_cop(total_amt))}</span></span>'
    )
    fire = ""
    if bool(row.get("contract_pending_artist_signature")):
        fire = '<span class="cal-overflow-fire-pending">Firma profesional pendiente</span>'
    left_cluster = (
        '<span class="cal-overflow-left">'
        f'<span class="cal-overflow-hm">{html_mod.escape(hm)}</span><span>·</span>'
        f"{svc_flag}<span>·</span>{pill}{staff_el}"
        f"{fire}</span>"
    )
    return f'<div class="cal-overflow-row{muted}">{left_cluster}{total_box}</div>'


def calendar_appt_line_html(
    row: dict[str, Any],
    counts_by_client: dict[str, int],
    *,
    long_name_from: int = 16,
) -> str:
    """HTML de una línea en celda mensual: hora | nombre | total compacto."""
    hm = appointment_time_hm(row.get("appointment_date", row.get("date")))
    nm = str(row.get("customer_name") or row.get("name") or "").strip() or "—"
    short = calendar_cell_customer_label(nm, long_from_len=long_name_from)
    cls = client_pill_class(row, counts_by_client)
    st_cl = str(row.get("status") or "").strip().lower()
    dim_cls = " cal-appt-line--muted" if st_cl == "cancelada" else ""
    total_amt, _, _ = appointment_financial_totals(row)
    price_lbl = calendar_month_compact_label(total_amt)
    pill_inner = (
        f'<span class="cli-pill {cls} cli-pill--cal-cell">{html_mod.escape(short)}</span>'
    )
    t_s = html_mod.escape(hm)
    staff_lbl = assigned_staff_label(row)
    staff_part = f" · {staff_lbl}" if staff_lbl != "—" else ""
    title = html_mod.escape(f"{hm} · {nm}{staff_part} · Total: {format_cop(total_amt)}")
    price_esc = html_mod.escape(price_lbl)
    return (
        f"<div class='cal-appt-line{dim_cls}' title='{title}'>"
        f"<span class='cal-appt-time'>{t_s}</span>"
        f"<span class='cal-appt-pill-wrap'>{pill_inner}</span>"
        f"<span class='cal-appt-total'>{price_esc}</span>"
        "</div>"
    )


def calendar_day_inner_body_html(
    day_rows: list[dict[str, Any]],
    counts_by_client: dict[str, int],
    *,
    team_layout: bool,
) -> tuple[str, int]:
    """HTML dentro de cal-day-inner: todas las citas del día."""
    if not day_rows:
        return "<div class='cal-day-empty'>—</div>", 0

    chunks: list[str] = []
    shown = 0

    if team_layout:
        for label, rows_g in group_calendar_day_rows_by_assigned_staff(day_rows):
            line_htmls = [calendar_appt_line_html(r, counts_by_client) for r in rows_g]
            shown += len(line_htmls)
            if line_htmls:
                chunks.append(
                    "<div class='cal-team-block'>"
                    f"<div class='cal-team-label'>{html_mod.escape(label)}</div>"
                    "<div class='cal-team-lines'>"
                    f"{''.join(line_htmls)}"
                    "</div></div>"
                )
    else:
        for r in day_rows:
            chunks.append(calendar_appt_line_html(r, counts_by_client))
            shown += 1

    return "".join(chunks), shown


__all__ = [
    "calendar_appt_line_html",
    "calendar_cell_customer_label",
    "calendar_day_inner_body_html",
    "calendar_overflow_row_html",
    "group_calendar_day_rows_by_assigned_staff",
]
