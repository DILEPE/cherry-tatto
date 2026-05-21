"""Reporte finanzas citas."""
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
from streamlit_app.report_work_performed import (
    load_piercing_survey_labels_cached,
    report_work_performed_text,
)


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


def render_procedure_value_bar_chart(filtered_items: list[dict[str, Any]]) -> None:
    """Barras: suma de total trabajo por tipo de servicio (procedimiento), según el filtro actual."""
    if not filtered_items:
        return
    by_svc: dict[str, float] = defaultdict(float)
    for row in filtered_items:
        svc = str(row.get("service_type", row.get("service", "")) or "").strip() or "Sin especificar"
        t_total, _, _ = appointment_financial_totals(row)
        by_svc[svc] += t_total
    ordered = sorted(by_svc.items(), key=lambda x: -x[1])
    categories = [k for k, _ in ordered]
    values = [float(v) for _, v in ordered]
    st.markdown("##### Valor por procedimiento")
    report_charts.render_vertical_bars(
        st,
        categories=categories,
        values=values,
        x_title="Tipo de servicio / procedimiento",
        y_title="Total trabajo (COP)",
        height=min(420, 140 + len(ordered) * 42),
        hovertemplate="<b>%{x}</b><br>%{y:,.0f} COP<extra></extra>",
        key="rep_fin_valor_procedimiento",
    )



def excel_fingerprint(rows: list[dict[str, Any]]) -> str:
    """Hash estable de los IDs de las filas filtradas (no del contenido completo)."""
    ids = sorted(int(r.get("id") or 0) for r in rows)
    return hashlib.md5(json.dumps(ids, separators=(",", ":")).encode()).hexdigest()[:16]


def get_excel_cached(rows: list[dict[str, Any]]) -> bytes:
    """
    Excel del filtro actual desde session_state si el conjunto de IDs no cambió;
    lo regenera y cachea si no hay hit. Elimina otros buffers _ap_xlsx_* previos.
    """
    fp = excel_fingerprint(rows)
    cache_key = f"_ap_xlsx_{fp}"
    hit = st.session_state.get(cache_key)
    if isinstance(hit, bytes) and len(hit) > 0:
        return hit

    for k in [
        k
        for k in st.session_state
        if isinstance(k, str) and k.startswith("_ap_xlsx_") and k != cache_key
    ]:
        st.session_state.pop(k, None)

    piercing_labels = load_piercing_survey_labels_cached(
        rows, cache_key="_ap_rep_piercing_labels"
    )
    data = citas_filtered_to_excel_bytes(
        rows, generated_at=datetime.now(), piercing_survey_labels=piercing_labels
    )
    st.session_state[cache_key] = data
    return data



def render_reporte_financiero_citas_body(
    items: list[dict[str, Any]],
    svc_values: list[str],
    status_values: list[str],
    *,
    client_history_key: Callable[..., str],
    render_row_actions: Callable[..., None],
) -> None:
    """Filtros, métricas, export Excel y tabla paginada (solo finanzas)."""
    st.markdown("##### Filtros")
    f1, f2, f3, f4, f5 = st.columns([1.3, 1.0, 1.0, 0.9, 0.9])
    with f1:
        st.text_input("Filtrar nombre", key="_ap_f_name", placeholder="Nombre cliente")
    with f2:
        st.selectbox("Servicio", options=["Todos", *svc_values], key="_ap_f_service")
    with f3:
        st.selectbox("Estado", options=["Todos", *status_values], key="_ap_f_status")
    with f4:
        st.date_input("Desde", key="_ap_f_from")
    with f5:
        st.date_input("Hasta", key="_ap_f_to")

    hist_counts_raw = st.session_state.get("_ap_hist_counts")
    hist_counts = dict(hist_counts_raw) if isinstance(hist_counts_raw, dict) else {}
    if not hist_counts and items:
        hist_counts = appointment_counts_by_client(items, client_history_key)

    filtered_items = apply_report_filters(items)
    piercing_survey = load_piercing_survey_labels_cached(
        filtered_items, cache_key="_ap_rep_piercing_labels"
    )

    total_trabajo = 0.0
    total_abonado = 0.0
    total_pendiente = 0.0
    total_credito_favor = 0.0
    for row in filtered_items:
        row_total, row_abonado, row_pendiente = appointment_financial_totals(row)
        total_trabajo += row_total
        total_abonado += row_abonado
        total_pendiente += row_pendiente
        total_credito_favor += customer_credit_from_row(row)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total trabajo", format_cop(total_trabajo))
    m2.metric("Total abonado", format_cop(total_abonado))
    m3.metric("Total saldo pendiente", format_cop(total_pendiente))
    m4.metric("Saldo a favor (filtro)", format_cop(total_credito_favor))

    render_procedure_value_bar_chart(filtered_items)

    _informe_dt = datetime.now()
    try:
        _xlsx_agenda = get_excel_cached(filtered_items)
    except Exception as e:
        _xlsx_agenda = b""
        if filtered_items:
            st.warning(f"No se pudo generar el Excel. Instala `openpyxl` en el venv: {e}")
    _dl_left, _dl_right = st.columns([4, 1])
    with _dl_right:
        st.download_button(
            label="Descargar Excel",
            help="Exporta financiero del filtro actual (nombre cliente y montos; hoja resumen).",
            data=_xlsx_agenda,
            file_name=(
                "Informe-finanzas-citas-"
                f"{_informe_dt.strftime('%Y-%m-%d-%H%M')}.xlsx"
            ),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            disabled=len(filtered_items) == 0 or len(_xlsx_agenda) == 0,
            key="btn_reporte_fin_xlsx",
        )

    st.markdown("##### Listado de citas")
    total = len(filtered_items)
    limit = int(st.session_state["_ap_limit"])
    page = int(st.session_state["_ap_page"])
    total_pages = max(1, (total + limit - 1) // limit)
    if page >= total_pages:
        page = max(0, total_pages - 1)
        st.session_state["_ap_page"] = page
    start = page * limit
    rows = filtered_items[start : start + limit]

    colw = [1.35, 0.95, 0.82, 1.05, 0.78, 0.72, 0.72, 0.85, 0.78, 0.72, 1.4]
    h1, h2, h3, h4, h5, h6, h7, h8, h9, h10, h11 = st.columns(colw)
    h1.markdown('<span class="ap-col-title">Nombre</span>', unsafe_allow_html=True)
    h2.markdown('<span class="ap-col-title">Artista</span>', unsafe_allow_html=True)
    h3.markdown('<span class="ap-col-title">Servicio</span>', unsafe_allow_html=True)
    h4.markdown('<span class="ap-col-title">Tipo trabajo / perforación</span>', unsafe_allow_html=True)
    h5.markdown('<span class="ap-col-title">Fecha y hora</span>', unsafe_allow_html=True)
    h6.markdown('<span class="ap-col-title">Total</span>', unsafe_allow_html=True)
    h7.markdown('<span class="ap-col-title">Abonado</span>', unsafe_allow_html=True)
    h8.markdown('<span class="ap-col-title">Pendiente</span>', unsafe_allow_html=True)
    h9.markdown('<span class="ap-col-title">A favor</span>', unsafe_allow_html=True)
    h10.markdown('<span class="ap-col-title">Estado</span>', unsafe_allow_html=True)
    h11.markdown('<span class="ap-col-title">Acciones</span>', unsafe_allow_html=True)
    for r in rows:
        c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11 = st.columns(colw)
        c1.markdown(customer_name_pill_html(r, hist_counts), unsafe_allow_html=True)
        c2.write(assigned_artist_display_name(r))
        c3.write(r.get("service_type", r.get("service", "")))
        c4.write(report_work_performed_text(r, piercing_survey))
        c5.write(format_appt_when(r.get("appointment_date", r.get("date", ""))))
        total_amount, deposit_amount, pending_balance = appointment_financial_totals(r)
        credito = customer_credit_from_row(r)
        c6.write(format_cop(total_amount))
        c7.write(format_cop(deposit_amount))
        c8.write(format_cop(pending_balance))
        c9.write("—" if credito <= 0 else format_cop(credito))
        status = str(r.get("status") or "Agendada")
        c10.markdown(status_pill_html(status), unsafe_allow_html=True)
        with c11:
            render_row_actions(r, show_firma=False)

    p1, p2, p3 = st.columns([1, 1, 2.5])
    with p1:
        st.write("")
        if st.button("◀", disabled=page <= 0, use_container_width=True, key="rep_ap_page_prev"):
            st.session_state["_ap_page"] = max(0, page - 1)
            st.rerun()
    with p2:
        st.write("")
        if st.button("▶", disabled=(page + 1) * limit >= total if total else True, use_container_width=True, key="rep_ap_page_next"):
            st.session_state["_ap_page"] = page + 1
            st.rerun()
    with p3:
        st.write("")
        st.caption(f"Página {page + 1}/{total_pages} · Total filtrado: {total} cita(s)")


__all__=['render_procedure_value_bar_chart','render_reporte_financiero_citas_body']
