"""Encuesta: resumen plot por pregunta."""
from __future__ import annotations
import unicodedata
from typing import Any, Optional
import streamlit as st
from app.domain.contract_kinds import SCOPE_LABEL_ES
from app.domain.survey_question_helpers import question_type_label_es, question_type_supports_distribution_chart
from streamlit_app import report_charts
from streamlit_app.cached_public_api import get_survey_question_stats_summary_cached
from streamlit_app.http_error_detail import format_http_error_detail


def truncate_survey_chart_label(s: str, max_len: int = 50) -> str:
    t = str(s).replace("\n", " ").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def survey_pie_chart_from_counts(
    counts: dict[str, int],
    *,
    chart_key: str,
    sort_key: Optional[Any] = None,
    reverse: bool = False,
    limit: Optional[int] = None,
) -> None:
    """Gráfica de torta (Plotly; mismo tema que barras del reporte)."""
    if not counts:
        return
    items = [(str(k), int(v)) for k, v in counts.items() if int(v) > 0]
    if not items:
        return
    if sort_key is not None:
        items.sort(key=sort_key, reverse=reverse)
    else:
        items.sort(key=lambda x: x[1], reverse=True)
    if limit is not None and limit > 0 and len(items) > limit:
        head = list(items[: max(0, limit - 1)])
        tail = items[limit - 1 :]
        otros = sum(v for _, v in tail)
        if otros > 0:
            head.append(("Otros", otros))
        items = head
    pie_labels = [truncate_survey_chart_label(k) for k, _ in items]
    pie_values = [v for _, v in items]
    if sum(pie_values) <= 0:
        return
    report_charts.render_pie(st, labels=pie_labels, values=pie_values, height=440, key=chart_key)


def normalize_survey_label_ascii_lower(s: str) -> str:
    """Compara etiquetas sin distinguir tildes ni mayúsculas."""
    t = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in t if not unicodedata.combining(c)).lower()


def survey_question_is_procedure_value_question(label: str) -> bool:
    """P. ej. «¿Cuánto es el valor de tu procedimiento?» → barras Plotly (mismo estilo que finanzas)."""
    n = normalize_survey_label_ascii_lower(label)
    return "procedimiento" in n and "valor" in n


def pairs_from_number_breakdown(nb: dict[str, int]) -> list[tuple[float, int]]:
    out: list[tuple[float, int]] = []
    for k, v in nb.items():
        try:
            out.append((float(k), int(v)))
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda x: x[0])
    return out


def survey_number_bar_chart_2d(pairs: list[tuple[float, int]], *, x_title: str, chart_key: str) -> None:
    """Barras respuesta numérica × frecuencia (Plotly, mismo estilo que el resto del reporte)."""
    if not pairs:
        return
    vals = [p[0] for p in pairs]
    ns = [p[1] for p in pairs]
    categories = [f"{v:g}" for v in vals]
    report_charts.render_vertical_bars(
        st,
        categories=categories,
        values=ns,
        x_title=x_title,
        y_title="Respuestas (n)",
        height=min(400, 140 + len(categories) * 36),
        hovertemplate="<b>Valor %{x}</b><br>%{y} respuesta(s)<extra></extra>",
        key=chart_key,
    )


def render_survey_question_stats_report() -> None:
    ok, code, raw = get_survey_question_stats_summary_cached()
    if not ok:
        det = format_http_error_detail(raw)
        st.warning(
            f"No se pudieron cargar las estadísticas de encuesta (HTTP {code}). "
            f"Ejecuta las migraciones `011`–`014` en `sql/` según corresponda. Detalle: {det}"
        )
        return
    if not isinstance(raw, list) or len(raw) == 0:
        st.caption("No hay preguntas registradas o la lista está vacía.")
        return
    for idx, row in enumerate(raw):
        if not isinstance(row, dict):
            continue
        qid = int(row.get("question_id") or idx)
        label = str(row.get("label") or "")
        qt = str(row.get("question_type") or "")
        ql = question_type_label_es(qt)
        ck = SCOPE_LABEL_ES.get(str(row.get("contract_kind") or "tattoo"), "—")
        rc = int(row.get("response_count") or 0)
        supports_chart = question_type_supports_distribution_chart(qt)
        st.divider()
        st.markdown(f"**{label}** · _{ql}_ · **{ck}** · n = **{rc}**")
        chart_shown = False

        rb = row.get("rating_breakdown")
        if qt == "rating_1_5" and isinstance(rb, dict) and rb:
            def _rk(item: tuple[str, int]) -> int:
                try:
                    return int(item[0])
                except (TypeError, ValueError):
                    return 0

            survey_pie_chart_from_counts(dict(rb), sort_key=_rk, chart_key=f"rep_survey_pie_{qid}_rating")
            chart_shown = True
            if row.get("avg_rating") is not None:
                st.metric("Promedio (1–5)", f"{float(row['avg_rating']):.2f}")
        elif qt == "yes_no":
            yc = int(row.get("yes_count") or 0)
            nc = int(row.get("no_count") or 0)
            c1, c2 = st.columns(2)
            c1.metric("Sí", yc)
            c2.metric("No", nc)
            if yc + nc > 0:
                survey_pie_chart_from_counts(
                    {"Sí": yc, "No": nc},
                    sort_key=lambda x: 0 if x[0] == "Sí" else 1,
                    chart_key=f"rep_survey_pie_{qid}_yesno",
                )
                chart_shown = True
        elif qt == "number":
            nb = row.get("number_breakdown")
            if isinstance(nb, dict) and nb:

                def _nk(item: tuple[str, int]) -> float:
                    try:
                        return float(item[0])
                    except (TypeError, ValueError):
                        return 0.0

                pairs = pairs_from_number_breakdown(dict(nb))
                if survey_question_is_procedure_value_question(label) and pairs:
                    survey_number_bar_chart_2d(
                        pairs,
                        x_title="Valor informado (tu procedimiento)",
                        chart_key=f"rep_survey_bar_{qid}_procval",
                    )
                    chart_shown = True
                else:
                    survey_pie_chart_from_counts(dict(nb), sort_key=_nk, chart_key=f"rep_survey_pie_{qid}_number")
                    chart_shown = True
            if row.get("avg_number") is not None:
                st.metric("Promedio numérico", f"{float(row['avg_number']):.4f}")
        elif qt in ("radio", "select", "checkbox"):
            cb = row.get("choice_breakdown")
            if isinstance(cb, dict) and cb:
                lim = 24 if qt == "checkbox" else 32
                survey_pie_chart_from_counts(dict(cb), limit=lim, chart_key=f"rep_survey_pie_{qid}_choice")
                chart_shown = True
                if qt == "checkbox":
                    st.caption(
                        "Casillas: cada **sector** puede ser una combinación guardada (texto/JSON); "
                        "no son opciones independientes. Si hay muchas categorías, el resto se agrupa en **Otros**."
                    )
        elif qt in ("text", "textarea", "text_short"):
            tc = int(row.get("text_response_count") or 0)
            st.caption(
                f"Pregunta de **texto libre**: no tiene categorías fijas adecuadas para una torta. "
                f"Respuestas no vacías: **{tc}**."
            )
        else:
            tc = int(row.get("text_response_count") or 0)
            st.caption(f"Respuestas con texto registrado: {tc}")

        if supports_chart and not chart_shown and rc > 0:
            st.info("Hay respuestas, pero aún no hay datos agregados para graficar (revisa el tipo de pregunta).")
        elif supports_chart and rc == 0:
            st.caption("Sin respuestas todavía.")

__all__=['render_survey_question_stats_report']
