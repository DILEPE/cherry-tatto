"""Panel: lista de usuarios asignables (caché en session_state)."""

from __future__ import annotations

from typing import Any

import streamlit as st

from streamlit_app.cached_public_api import get_panel_users_assignable_cached


def ensure_assignable_staff() -> list[dict[str, Any]]:
    cached = st.session_state.get("_ap_assignable_staff")
    if isinstance(cached, list):
        return cached
    ok, _, data = get_panel_users_assignable_cached()
    if ok and isinstance(data, list):
        st.session_state["_ap_assignable_staff"] = data
        return data
    return []


__all__ = ["ensure_assignable_staff"]
