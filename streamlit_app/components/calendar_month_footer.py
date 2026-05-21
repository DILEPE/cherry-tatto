"""Pie del mes (HTML + query_params) para agendar y abrir citas sin widgets ocultos."""

from __future__ import annotations

import html as html_mod

from streamlit_app.components.calendar_query_nav import (
    calendar_book_open_href,
    calendar_book_control_html,
)


def cal_month_book_query_href(y: int, m: int, d: int) -> str:
    return calendar_book_open_href(y, m, d)


def cal_month_appt_query_href(appt_id: int) -> str:
    from streamlit_app.components.calendar_query_nav import calendar_appt_open_href

    return calendar_appt_open_href(appt_id)


def calendar_footer_book_html(
    y: int,
    m: int,
    d: int,
    *,
    disabled_footer: bool,
    title_esc: str,
) -> str:
    """Botón «+ Agregar cita» (mismo aspecto en mes y semana)."""
    return calendar_book_control_html(
        y, m, d, disabled_footer=disabled_footer, title_esc=title_esc
    )


def calendar_month_footer_strip_html(
    y: int,
    m: int,
    d: int,
    *,
    disabled_footer: bool,
    title_esc: str,
) -> str:
    """Pie de celda mensual: día visible + enlace o botón deshabilitado para agendar."""
    strip_cls = "cal-cell-footer-strip"
    if disabled_footer:
        strip_cls += " cal-footer-strip-disabled"
    book_el = calendar_footer_book_html(
        y, m, d, disabled_footer=disabled_footer, title_esc=title_esc
    )
    return (
        f'<div class="{strip_cls}" role="presentation">'
        f'<span class="cal-footer-daynum">{html_mod.escape(str(d))}</span>'
        f"{book_el}"
        "</div>"
    )


def calendar_week_header_book_strip_html(
    y: int,
    m: int,
    d: int,
    *,
    disabled_footer: bool,
    title_esc: str,
) -> str:
    """Pie de agendar bajo el día en cabecera semanal (mismas clases que el mes)."""
    strip_cls = "cal-cell-footer-strip twg-h-footer-strip"
    if disabled_footer:
        strip_cls += " cal-footer-strip-disabled"
    book_el = calendar_footer_book_html(
        y, m, d, disabled_footer=disabled_footer, title_esc=title_esc
    )
    return f'<div class="{strip_cls}" role="presentation">{book_el}</div>'


__all__ = [
    "cal_month_appt_query_href",
    "cal_month_book_query_href",
    "calendar_footer_book_html",
    "calendar_month_footer_strip_html",
    "calendar_week_header_book_strip_html",
]
