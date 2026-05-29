"""Invalidación explícita de cachés de citas/abonos en session_state."""

from __future__ import annotations

from typing import Any

import streamlit as st

from streamlit_app import api_client
from streamlit_app.state.appointment_keys import (
    KEY_FIN_PAYMENTS_PFX,
    KEY_RECEIPTS_LIST_PFX,
    KEY_RECEIPT_PDF_PFX,
)


def purge_appointment_payment_caches() -> None:
    """Elimina caches `_ap_fin_payments_<id>` (historial GET abonos por cita)."""
    for k in list(st.session_state.keys()):
        if isinstance(k, str) and k.startswith(KEY_FIN_PAYMENTS_PFX):
            st.session_state.pop(k, None)


def purge_appointment_receipt_caches() -> None:
    """Elimina caches de listados de recibos y blobs PDF precargados."""
    for k in list(st.session_state.keys()):
        if not isinstance(k, str):
            continue
        if k.startswith(KEY_RECEIPTS_LIST_PFX) or k.startswith(KEY_RECEIPT_PDF_PFX):
            st.session_state.pop(k, None)


def get_appointment_payments_cached(appt_id: int) -> tuple[bool, int, Any]:
    """Un GET por cita y sesión (se invalida al refrescar citas o tras guardar montos)."""
    key = f"{KEY_FIN_PAYMENTS_PFX}{int(appt_id)}"
    hit = st.session_state.get(key)
    if isinstance(hit, tuple) and len(hit) == 3:
        return hit[0], hit[1], hit[2]
    with st.spinner("Cargando historial de abonos…"):
        ok_p, code_p, payments = api_client.get_appointment_payments(appt_id)
    st.session_state[key] = (ok_p, code_p, payments)
    return ok_p, code_p, payments


__all__ = ["get_appointment_payments_cached", "purge_appointment_payment_caches", "purge_appointment_receipt_caches"]
