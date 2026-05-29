"""
Contrato de session_state para citas y reporte (prefijo `_ap_`).

Mantén las claves alineadas con `citas_tab`: documentación central para refactors.

Notas:
- Lista de agenda: `_ap_list`; error de último GET: `_ap_err`.
- Tras escrituras desde la API usar `_ap_reload` e invalidación explícita de cachés.
"""

from __future__ import annotations

# Lista y fetch
_KEY_LIST = "_ap_list"
_KEY_ERR = "_ap_err"
_KEY_RELOAD = "_ap_reload"
_KEY_LAST_FETCH_QID = "_ap_last_fetch_qid"
# Precálculo tras sync (performance)
_KEY_HIST_COUNTS = "_ap_hist_counts"
_KEY_SVC_VALUES = "_ap_svc_values"

# Cachés abonos / recibos (prefijo + id numérico)
_KEY_FIN_PAYMENTS_PFX = "_ap_fin_payments_"
_KEY_RECEIPTS_LIST_PFX = "_ap_receipts_list_"
_KEY_RECEIPT_PDF_PFX = "_ap_receipt_pdf_"
# Toast / mensajes tras acciones (persisten hasta consumir)
_KEY_ACTION_INFO = "_ap_action_info"
_KEY_TOAST_FETCH_ERR = "_ap_toast_fetch_err"
_KEY_TOAST_FIN_SAVE_ERR = "_ap_toast_fin_save_err"

# Export para imports explícitos
KEY_LIST = _KEY_LIST
KEY_ERR = _KEY_ERR
KEY_RELOAD = _KEY_RELOAD
KEY_LAST_FETCH_QID = _KEY_LAST_FETCH_QID
KEY_HIST_COUNTS = _KEY_HIST_COUNTS
KEY_SVC_VALUES = _KEY_SVC_VALUES
KEY_FIN_PAYMENTS_PFX = _KEY_FIN_PAYMENTS_PFX
KEY_RECEIPTS_LIST_PFX = _KEY_RECEIPTS_LIST_PFX
KEY_RECEIPT_PDF_PFX = _KEY_RECEIPT_PDF_PFX
KEY_ACTION_INFO = _KEY_ACTION_INFO
KEY_TOAST_FETCH_ERR = _KEY_TOAST_FETCH_ERR
KEY_TOAST_FIN_SAVE_ERR = _KEY_TOAST_FIN_SAVE_ERR

__all__ = [
    "KEY_ACTION_INFO",
    "KEY_ERR",
    "KEY_FIN_PAYMENTS_PFX",
    "KEY_HIST_COUNTS",
    "KEY_LAST_FETCH_QID",
    "KEY_LIST",
    "KEY_RECEIPTS_LIST_PFX",
    "KEY_RECEIPT_PDF_PFX",
    "KEY_RELOAD",
    "KEY_TOAST_FETCH_ERR",
    "KEY_TOAST_FIN_SAVE_ERR",
    "KEY_SVC_VALUES",
]
