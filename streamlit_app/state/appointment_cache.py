"""Invalidación explícita de cachés de citas/abonos en session_state."""

from __future__ import annotations

import streamlit as st

from streamlit_app.state.appointment_keys import KEY_FIN_PAYMENTS_PFX, KEY_RECEIPT_PDF_PFX, KEY_RECEIPTS_LIST_PFX


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


__all__ = ["purge_appointment_payment_caches", "purge_appointment_receipt_caches"]
