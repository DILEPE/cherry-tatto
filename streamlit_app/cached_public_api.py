"""
Caché de proceso (`st.cache_data`) solo para respuestas **globales** del panel.

No uses esto para datos por sesión o por usuario (p. ej. listas de citas filtradas);
ahí conviene `st.session_state` + invalidación explícita.
"""
from __future__ import annotations

from typing import Any, Tuple

import streamlit as st

from streamlit_app import api_client


@st.cache_data(ttl=90, show_spinner=False)
def get_survey_question_stats_summary_cached() -> Tuple[bool, int, Any]:
    return api_client.get_survey_question_stats_summary()


@st.cache_data(ttl=120, show_spinner=False)
def get_panel_users_assignable_cached() -> Tuple[bool, int, Any]:
    return api_client.get_panel_users_assignable_for_appointments()
