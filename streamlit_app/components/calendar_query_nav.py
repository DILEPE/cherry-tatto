"""Clic en «Ver cita» / agendar dentro del HTML del calendario → componente bidireccional."""

from __future__ import annotations

import html as html_mod
import os
from urllib.parse import urlencode

import streamlit as st
import streamlit.components.v1 as components

# Componente bidireccional: intercepta clics en .cal-query-nav y devuelve la
# acción a Python vía Streamlit.setComponentValue() sin navegar por URL.
_CAL_NAV_COMPONENT_DIR = os.path.join(os.path.dirname(__file__), "_cal_nav_component")
_cal_nav_component = components.declare_component(
    "cherry_cal_nav_v5", path=_CAL_NAV_COMPONENT_DIR
)


def _query_params_flat() -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        raw = st.query_params.to_dict()
    except AttributeError:
        raw = dict(st.query_params)
    for k, v in raw.items():
        if isinstance(v, list):
            out[str(k)] = str(v[0]) if v else ""
        else:
            out[str(k)] = str(v)
    return out


def calendar_appt_open_href(appt_id: int) -> str:
    qp = _query_params_flat()
    qp.pop("cal_book", None)
    qp["cal_appt_id"] = str(int(appt_id))
    return "?" + urlencode(qp)


def calendar_book_open_href(y: int, m: int, d: int) -> str:
    qp = _query_params_flat()
    qp.pop("cal_appt_id", None)
    qp["cal_book"] = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    return "?" + urlencode(qp)


def calendar_appt_open_control_html(
    appt_id: int,
    *,
    extra_class: str = "",
    monday_iso: str = "",
) -> str:
    """Botón «Ver cita» en la celda; el puente JS fusiona ?cal_appt_id= en la URL."""
    _ = monday_iso
    aid = int(appt_id)
    if aid <= 0:
        return ""
    cls = "cal-appt-slot-link cal-query-nav"
    if extra_class.strip():
        cls += f" {extra_class.strip()}"
    href = html_mod.escape(calendar_appt_open_href(aid), quote=True)
    return (
        f'<button type="button" class="{cls}" '
        f'data-cal-nav="appt" data-cal-appt-id="{aid}" data-cal-href="{href}" '
        f'aria-label="Ver cita">'
        '<span class="cal-appt-slot-link-play" aria-hidden="true">▶</span>'
        "<span>Ver cita</span>"
        "</button>"
    )


def calendar_book_control_html(
    y: int,
    m: int,
    d: int,
    *,
    disabled_footer: bool,
    title_esc: str,
    css_class: str = "cal-footer-book",
) -> str:
    if disabled_footer:
        return (
            f'<span class="{css_class} cal-footer-book--disabled" '
            f'title="{title_esc}" aria-label="{title_esc}">'
            "+ Agregar cita</span>"
        )
    href = html_mod.escape(calendar_book_open_href(y, m, d), quote=True)
    return (
        f'<button type="button" class="{css_class} cal-query-nav" '
        f'data-cal-nav="book" data-cal-y="{int(y)}" data-cal-m="{int(m)}" data-cal-d="{int(d)}" '
        f'data-cal-href="{href}" title="{title_esc}" aria-label="{title_esc}">'
        "+ Agregar cita</button>"
    )


def inject_calendar_query_nav_bridge() -> dict | None:
    """Componente bidireccional: intercepta clics en .cal-query-nav y devuelve la acción.

    Retorna un dict ``{type: "appt", id: int}`` o ``{type: "book", y, m, d}`` cuando
    el usuario hace clic en «Ver cita» o «Agendar», o ``None`` si no hubo acción.
    La acción se lee desde ``st.session_state["cal_nav_bridge"]`` en el rerun siguiente.
    """
    return _cal_nav_component(key="cal_nav_bridge", default=None)


__all__ = [
    "calendar_appt_open_control_html",
    "calendar_appt_open_href",
    "calendar_book_control_html",
    "calendar_book_open_href",
    "inject_calendar_query_nav_bridge",
]

# calendar_appt_open_href / calendar_book_open_href se mantienen para que el HTML
# incluya data-cal-href como metadato (sin usarlo para navegar).

