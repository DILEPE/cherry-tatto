"""Diálogo «Buscar cita» en el tab Citas (nombre, recibo, documento)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable, Optional

import streamlit as st

from streamlit_app import api_client
from streamlit_app.appointment_dates import appointment_row_date, format_appointment_datetime_table_es
from streamlit_app.appointment_staff_labels import assigned_artist_display_name
from streamlit_app.http_error_detail import format_http_error_detail

_SEARCH_FIELDS: dict[str, str] = {
    "name": "Nombre",
    "receipt": "Número de recibo",
    "document": "Número de documento",
}
_SEARCH_FIELD_KEYS = list(_SEARCH_FIELDS.keys())
_SEARCH_PAGE_SIZE = 10


def _close_search_dialog() -> None:
    st.session_state.pop("_ap_search_dlg", None)


def navigate_calendar_to_appointment(
    hit: dict[str, Any],
    *,
    filter_for_role: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
) -> None:
    """Cierra el buscador, posiciona el calendario en la fecha y abre la ficha de la cita."""
    aid = int(hit.get("id") or 0)
    if aid <= 0:
        return
    ok, code, data = api_client.get_appointment(aid)
    row: dict[str, Any]
    if ok and isinstance(data, dict):
        row = dict(data)
    else:
        row = dict(hit)
    row["id"] = aid

    lst = list(st.session_state.get("_ap_list") or [])
    replaced = False
    for i, existing in enumerate(lst):
        if int(existing.get("id", 0) or 0) == aid:
            lst[i] = row
            replaced = True
            break
    if not replaced:
        lst.insert(0, row)
    st.session_state["_ap_list"] = filter_for_role(lst)

    try:
        d = appointment_row_date(row.get("appointment_date", row.get("date")))
    except (TypeError, ValueError):
        d = date.today()
    st.session_state["_ap_cal_ym"] = [d.year, d.month]
    st.session_state["_ap_week_monday"] = d - timedelta(days=d.weekday())

    st.session_state["_cal_focus_appt_id"] = aid
    st.session_state.pop("_cal_overflow_day", None)
    _close_search_dialog()
    st.rerun()


def _run_search(*, assigned_user_id: Optional[int]) -> None:
    field_key = str(st.session_state.get("_ap_search_field") or "name")
    if field_key not in _SEARCH_FIELD_KEYS:
        field_key = "name"
    term = str(st.session_state.get("_ap_search_q") or "").strip()
    if not term:
        st.session_state["_ap_search_result"] = None
        st.session_state["_ap_search_err"] = "Indica un valor para buscar."
        return
    page = max(0, int(st.session_state.get("_ap_search_page") or 0))
    with st.spinner("Buscando…"):
        ok, code, data = api_client.search_appointments(
            field=field_key,
            q=term,
            limit=_SEARCH_PAGE_SIZE,
            offset=page * _SEARCH_PAGE_SIZE,
            assigned_panel_user_id=assigned_user_id,
        )
    if ok and isinstance(data, dict):
        st.session_state["_ap_search_result"] = data
        st.session_state["_ap_search_err"] = None
    else:
        st.session_state["_ap_search_result"] = None
        st.session_state["_ap_search_err"] = format_http_error_detail(data) if data else f"HTTP {code}"


@st.dialog("Buscar cita", width="large", dismissible=False)
def dialog_buscar_cita(
    *,
    query_assigned_user_id: Callable[[], Optional[int]],
    filter_for_role: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
) -> None:
    st.markdown('<div class="ap-search-dialog-root" aria-hidden="true"></div>', unsafe_allow_html=True)

    if "_ap_search_field" not in st.session_state:
        st.session_state["_ap_search_field"] = "name"
    if "_ap_search_q" not in st.session_state:
        st.session_state["_ap_search_q"] = ""
    if "_ap_search_page" not in st.session_state:
        st.session_state["_ap_search_page"] = 0

    t1, t2, t3 = st.columns([1.1, 2.2, 0.75], vertical_alignment="bottom")
    with t1:
        st.selectbox(
            "Buscar por *",
            options=_SEARCH_FIELD_KEYS,
            format_func=lambda k: _SEARCH_FIELDS[k],
            key="_ap_search_field",
        )
    with t2:
        st.text_input("Valor para buscar *", key="_ap_search_q", placeholder="Texto a buscar")
    with t3:
        if st.button(
            "Buscar",
            type="primary",
            use_container_width=True,
            icon=":material/search:",
            key="_ap_search_btn_run",
        ):
            st.session_state["_ap_search_page"] = 0
            _run_search(assigned_user_id=query_assigned_user_id())
            st.rerun()

    err = st.session_state.get("_ap_search_err")
    if err:
        st.warning(str(err))

    payload = st.session_state.get("_ap_search_result")
    if not isinstance(payload, dict):
        if st.button("Cancelar", use_container_width=True, key="_ap_search_cancel_empty"):
            _close_search_dialog()
            st.rerun()
        return

    items_raw = list(payload.get("items") or [])
    items = filter_for_role([dict(x) for x in items_raw if isinstance(x, dict)])
    total = int(payload.get("total") or 0)
    page = max(0, int(st.session_state.get("_ap_search_page") or 0))
    total_pages = max(1, (total + _SEARCH_PAGE_SIZE - 1) // _SEARCH_PAGE_SIZE)

    st.markdown('<p class="ap-search-table-title">Citas</p>', unsafe_allow_html=True)
    h1, h2, h3, h4, h5 = st.columns([1.35, 0.85, 1.35, 1.2, 0.55], vertical_alignment="center")
    h1.markdown('<span class="ap-search-col-head">Fecha</span>', unsafe_allow_html=True)
    h2.markdown('<span class="ap-search-col-head">Recibo #</span>', unsafe_allow_html=True)
    h3.markdown('<span class="ap-search-col-head">Cliente</span>', unsafe_allow_html=True)
    h4.markdown('<span class="ap-search-col-head">Artista</span>', unsafe_allow_html=True)
    h5.markdown('<span class="ap-search-col-head">Ir a fecha</span>', unsafe_allow_html=True)

    for idx, raw in enumerate(items):
        if not isinstance(raw, dict):
            continue
        hit = dict(raw)
        aid = int(hit.get("id") or 0)
        c1, c2, c3, c4, c5 = st.columns([1.35, 0.85, 1.35, 1.2, 0.55], vertical_alignment="center")
        with c1:
            st.write(format_appointment_datetime_table_es(hit.get("appointment_date")))
        with c2:
            st.write(str(hit.get("receipt_label") or "—"))
        with c3:
            st.write(str(hit.get("customer_name") or "—"))
        with c4:
            st.write(assigned_artist_display_name(hit))
        with c5:
            if st.button(
                "",
                key=f"_ap_search_go_{aid}_{page}_{idx}",
                icon=":material/event:",
                use_container_width=True,
            ):
                navigate_calendar_to_appointment(hit, filter_for_role=filter_for_role)

    if total <= 0:
        st.caption("Sin resultados para este criterio.")
    else:
        p_prev, p_info, p_next = st.columns([1, 3, 1])
        with p_prev:
            if st.button("◀", disabled=page <= 0, key="_ap_search_page_prev"):
                st.session_state["_ap_search_page"] = page - 1
                _run_search(assigned_user_id=query_assigned_user_id())
                st.rerun()
        with p_info:
            st.caption(f"({page + 1} de {total_pages}) · {total} cita(s)")
        with p_next:
            if st.button("▶", disabled=(page + 1) >= total_pages, key="_ap_search_page_next"):
                st.session_state["_ap_search_page"] = page + 1
                _run_search(assigned_user_id=query_assigned_user_id())
                st.rerun()

    st.markdown("---")
    if st.button("Cancelar", use_container_width=True, key="_ap_search_cancel"):
        _close_search_dialog()
        st.rerun()


__all__ = ["dialog_buscar_cita", "navigate_calendar_to_appointment"]
