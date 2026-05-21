"""Calendario mensual principal (fragment Streamlit) del panel Citas."""

from __future__ import annotations

import calendar
import html as html_mod
from datetime import date
from typing import Any, Callable

import streamlit as st

from streamlit_app.components.calendar_cells import calendar_day_inner_body_html
from streamlit_app.components.calendar_month_footer import (
    calendar_month_footer_strip_html,
    inject_calendar_month_appt_click_bridge,
    inject_calendar_month_footer_bridge,
    render_calendar_month_hidden_appt_open_buttons,
    render_calendar_month_hidden_book_widgets,
)

# Índice 1-based alineado con `datetime.month` (índice 0 vacío).
MONTHS_ES = (
    "",
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
)


def weekday_headers_es() -> list[str]:
    return ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


def calendar_fragment_rerun() -> None:
    """Reejecutar solo el fragment del calendario si la versión de Streamlit lo permite."""
    try:
        st.rerun(scope="fragment")
    except TypeError:
        st.rerun()


@st.fragment
def render_main_calendar(
    buckets: dict[tuple[int, int, int], list[dict[str, Any]]],
    counts_by_client: dict[str, int],
    *,
    team_layout: bool = False,
    clear_calendar_dialog_focus: Callable[[], None],
    panel_is_technician_role: Callable[[], bool],
    pop_booking_document_session: Callable[[], None],
) -> None:
    """Vista principal: mes con citas por día; pie HTML delega en botones ocultos."""
    ym_key = "_ap_cal_ym"
    today = date.today()
    if ym_key not in st.session_state:
        st.session_state[ym_key] = (today.year, today.month)
    y, m = st.session_state[ym_key]

    st.markdown("##### Calendario de citas")

    n1, n2, n3 = st.columns([1, 3, 1])
    with n1:
        if st.button("◀ Mes", key="cal_main_prev_m"):
            clear_calendar_dialog_focus()
            if m <= 1:
                st.session_state[ym_key] = (y - 1, 12)
            else:
                st.session_state[ym_key] = (y, m - 1)
            calendar_fragment_rerun()
    with n2:
        st.markdown(
            f"<div style='text-align:center;font-weight:600;font-size:1.05rem'>"
            f"{html_mod.escape(str(MONTHS_ES[m]))} {html_mod.escape(str(y))}</div>",
            unsafe_allow_html=True,
        )
    with n3:
        if st.button("Mes ▶", key="cal_main_next_m"):
            clear_calendar_dialog_focus()
            if m >= 12:
                st.session_state[ym_key] = (y + 1, 1)
            else:
                st.session_state[ym_key] = (y, m + 1)
            calendar_fragment_rerun()

    hdr_cells = st.columns(7, gap=None)
    for i, lab in enumerate(weekday_headers_es()):
        hdr_cells[i].markdown(
            f"<div class='cal-m-whcell'>{html_mod.escape(lab)}</div>",
            unsafe_allow_html=True,
        )
    weeks_grid = calendar.monthcalendar(y, m)
    allow_footer_book = panel_is_technician_role() is False
    for week in weeks_grid:
        row_cells = st.columns(7, gap=None)
        for i, d in enumerate(week):
            with row_cells[i]:
                if d == 0:
                    st.markdown(
                        "<div class='cal-cell-spacer cal-cell-spacer--month'></div>",
                        unsafe_allow_html=True,
                    )
                else:
                    day_rows = buckets.get((y, m, d), [])
                    picked_cell = date(y, m, d)
                    today_cls = " cal-cell-today" if picked_cell == today else ""
                    body, _shown = calendar_day_inner_body_html(
                        day_rows,
                        counts_by_client,
                        team_layout=team_layout,
                    )
                    is_past = picked_cell < date.today()
                    footer_off = is_past or not allow_footer_book
                    fh = html_mod.escape(
                        "Los tatuadores y perforadores no pueden agendar desde el calendario"
                        if not allow_footer_book
                        else (
                            "No se pueden agendar citas en fechas pasadas"
                            if is_past
                            else f"Agendar cita · {picked_cell.strftime('%d/%m/%Y')}"
                        )
                    )
                    footer_html = calendar_month_footer_strip_html(
                        y,
                        m,
                        d,
                        disabled_footer=footer_off,
                        title_esc=fh,
                    )
                    st.markdown(
                        f"<div class='cal-cell cal-cell--month{today_cls}'>"
                        f"<div class='cal-cell-head'><span class='cal-cell-daynum'>"
                        f"{html_mod.escape(str(d))}</span></div>"
                        f"<div class='cal-day-inner'>{body}</div>"
                        f"{footer_html}</div>",
                        unsafe_allow_html=True,
                    )
    render_calendar_month_hidden_appt_open_buttons(
        buckets,
        clear_calendar_dialog_focus=clear_calendar_dialog_focus,
    )
    render_calendar_month_hidden_book_widgets(
        y,
        m,
        weeks_grid,
        panel_is_technician_role=panel_is_technician_role,
        clear_calendar_dialog_focus=clear_calendar_dialog_focus,
        pop_booking_document_session=pop_booking_document_session,
    )
    inject_calendar_month_appt_click_bridge()
    inject_calendar_month_footer_bridge()


__all__ = [
    "MONTHS_ES",
    "calendar_fragment_rerun",
    "render_main_calendar",
    "weekday_headers_es",
]
