"""Opciones de tienda para selects (desde API por id)."""

from __future__ import annotations

from typing import Any

import streamlit as st

from streamlit_app import api_client

_STORE_CHOICES_CACHE_KEY = "_store_choices_cache"


def store_label_map(items: list[dict[str, Any]]) -> dict[int, str]:
    out: dict[int, str] = {}
    for row in items:
        try:
            sid = int(row.get("id") or 0)
        except (TypeError, ValueError):
            continue
        if sid <= 0:
            continue
        name = str(row.get("name") or f"#{sid}").strip()
        out[sid] = name
    return out


def load_store_choices(
    *,
    include_inactive: bool = False,
    use_session_cache: bool = True,
) -> tuple[list[int], dict[int, str]]:
    """IDs de tienda y etiquetas (nombre) para selectbox."""
    cache_key = f"{_STORE_CHOICES_CACHE_KEY}{'_all' if include_inactive else ''}"
    if use_session_cache:
        hit = st.session_state.get(cache_key)
        if isinstance(hit, tuple) and len(hit) == 2:
            ids, labels = hit
            if isinstance(ids, list) and isinstance(labels, dict):
                return [int(x) for x in ids], {int(k): str(v) for k, v in labels.items()}

    ok, _code, data = api_client.get_stores(include_inactive=include_inactive)
    if ok and isinstance(data, list) and data:
        labels = store_label_map(data)
        ids = sorted(labels.keys(), key=lambda i: labels[i].lower())
        if use_session_cache:
            st.session_state[cache_key] = (ids, labels)
        return ids, labels

    return [], {}


def invalidate_store_choices_cache() -> None:
    for k in [x for x in st.session_state if isinstance(x, str) and x.startswith(_STORE_CHOICES_CACHE_KEY)]:
        st.session_state.pop(k, None)


def store_display_label(store_id: int, labels: dict[int, str]) -> str:
    try:
        sid = int(store_id)
    except (TypeError, ValueError):
        return "—"
    return labels.get(sid, f"#{sid}")


__all__ = [
    "invalidate_store_choices_cache",
    "load_store_choices",
    "store_display_label",
    "store_label_map",
]
