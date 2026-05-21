"""Carga y caché de etiquetas «tipo trabajo / perforación» para el reporte financiero."""

from __future__ import annotations

from typing import Any

import streamlit as st

from app.domain.contract_kinds import appointment_to_contract_kind
from app.domain.piercing_procedure_labels import build_piercing_type_index
from app.domain.work_performed_label import work_performed_label
from streamlit_app import api_client

_PIERCING_TYPE_INDEX_KEY = "_ap_piercing_type_index"


def piercing_appointment_ids(rows: list[dict[str, Any]]) -> list[int]:
    out: list[int] = []
    for row in rows:
        if appointment_to_contract_kind(row) != "piercing":
            continue
        try:
            aid = int(row.get("id") or 0)
        except (TypeError, ValueError):
            continue
        if aid > 0:
            out.append(aid)
    return sorted(set(out))


def fetch_piercing_survey_labels(appointment_ids: list[int]) -> dict[int, str]:
    if not appointment_ids:
        return {}
    ok, _code, data = api_client.get_appointments_work_performed_labels(appointment_ids)
    if not ok or not isinstance(data, dict):
        return {}
    parsed: dict[int, str] = {}
    for k, v in data.items():
        try:
            aid = int(k)
        except (TypeError, ValueError):
            continue
        text = str(v or "").strip()
        if aid > 0 and text:
            parsed[aid] = text
    return parsed


def load_piercing_survey_labels_cached(
    rows: list[dict[str, Any]],
    *,
    cache_key: str,
) -> dict[int, str]:
    """Evita repetir GET por lote cuando el filtro del reporte no cambió."""
    ids = piercing_appointment_ids(rows)
    fp = ",".join(str(i) for i in ids)
    hit = st.session_state.get(cache_key)
    if isinstance(hit, tuple) and len(hit) == 2 and hit[0] == fp:
        cached = hit[1]
        return dict(cached) if isinstance(cached, dict) else {}
    labels = fetch_piercing_survey_labels(ids)
    st.session_state[cache_key] = (fp, labels)
    return labels


def get_piercing_type_index_cached() -> dict[str, str]:
    """Índice catálogo Helix / Lóbulo / Nostril… (misma sesión, sin otra llamada API)."""
    hit = st.session_state.get(_PIERCING_TYPE_INDEX_KEY)
    if isinstance(hit, dict) and hit:
        return dict(hit)
    idx = build_piercing_type_index()
    st.session_state[_PIERCING_TYPE_INDEX_KEY] = idx
    return idx


def report_work_performed_text(
    row: dict[str, Any],
    piercing_survey: dict[int, str],
) -> str:
    return work_performed_label(
        row,
        piercing_survey_by_appointment=piercing_survey,
        piercing_type_index=get_piercing_type_index_cached(),
    )


__all__ = [
    "fetch_piercing_survey_labels",
    "load_piercing_survey_labels_cached",
    "piercing_appointment_ids",
    "report_work_performed_text",
]
