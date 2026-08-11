from __future__ import annotations

import base64
import datetime
import json
import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)


def _http_2xx(status: int) -> bool:
    return 200 <= int(status) < 300


def _form_field_str(val: object) -> str:
    if val is None:
        return ""
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False)
    return str(val)


def _payment_receipt_amount_positive(data: dict[str, object]) -> bool:
    """Solo notificar recibos de pago si el importe del movimiento es > 0."""
    raw = data.get("amount")
    try:
        return float(raw if raw is not None else 0) > 0
    except (TypeError, ValueError):
        return False


class NotificationService:
    """Servicio para comunicarse con webhooks de n8n.

    Los recibos PDF (`payment_receipt_pdf`) y los cuidados/consentimiento (`contract_consent_pdf`)
    se envían **igual**: multipart/form-data con el archivo en el campo binario ``data``
    y el resto de metadatos como campos de texto (sin reenviar ``pdf_base64``).

    Para solo JSON con ``pdf_base64`` en recibos: ``N8N_PAYMENT_RECEIPT_TRANSPORT=json``.
    Los cuidados usan el mismo criterio con ``N8N_CONTRACT_CONSENT_TRANSPORT`` (por defecto
    el mismo valor que el recibo / multipart).
    """

    def __init__(
        self,
        webhook_url: Optional[str],
        receipt_webhook_url: Optional[str] = None,
        contract_consent_webhook_url: Optional[str] = None,
    ):
        self.webhook_url = (webhook_url or "").strip() or None
        self.receipt_webhook_url = (receipt_webhook_url or "").strip() or None
        self.contract_consent_webhook_url = (contract_consent_webhook_url or "").strip() or None

    def _resolve_url(self, event: str) -> Optional[str]:
        if event == "payment_receipt_pdf":
            return self.receipt_webhook_url or self.webhook_url
        if event == "contract_consent_pdf":
            return (
                self.contract_consent_webhook_url
                or self.receipt_webhook_url
                or self.webhook_url
            )
        return self.webhook_url

    def _pdf_transport(self, event: str) -> str:
        """Mismo transporte que el recibo (multipart por defecto)."""
        if event == "payment_receipt_pdf":
            return (os.getenv("N8N_PAYMENT_RECEIPT_TRANSPORT") or "multipart").strip().lower()
        if event == "contract_consent_pdf":
            # Por defecto idéntico al recibo; se puede forzar con N8N_CONTRACT_CONSENT_TRANSPORT.
            explicit = (os.getenv("N8N_CONTRACT_CONSENT_TRANSPORT") or "").strip().lower()
            if explicit:
                return explicit
            return (os.getenv("N8N_PAYMENT_RECEIPT_TRANSPORT") or "multipart").strip().lower()
        return "json"

    def notify(self, event: str, data: dict[str, object]) -> bool:
        url = self._resolve_url(event)
        if not url:
            logger.warning(
                "n8n: sin URL configurada para event=%s "
                "(defina N8N_WEBHOOK_URL y/o N8N_RECEIPT_WEBHOOK_URL según el caso).",
                event,
            )
            return False

        if event == "payment_receipt_pdf" and not _payment_receipt_amount_positive(data):
            logger.warning(
                "n8n: no se envía payment_receipt_pdf porque amount<=0 o no numérico (payload=%s)",
                {k: data.get(k) for k in ("appointment_id", "amount", "kind")},
            )
            return False

        if event in ("payment_receipt_pdf", "contract_consent_pdf"):
            transport = self._pdf_transport(event)
            if transport in ("json", "application/json"):
                payload = {
                    "event": event,
                    "data": data,
                    "timestamp": datetime.datetime.now().isoformat(),
                }
                try:
                    response = requests.post(url, json=payload, timeout=120)
                    if not _http_2xx(response.status_code):
                        logger.warning(
                            "n8n %s (JSON): HTTP %s desde %s — %s",
                            event,
                            response.status_code,
                            url,
                            (response.text or "")[:800],
                        )
                    return _http_2xx(response.status_code)
                except Exception:
                    logger.exception("n8n %s (JSON): error de red hacia %s", event, url)
                    return False

            # Igual que el recibo: multipart, archivo en campo «data».
            b64 = data.get("pdf_base64")
            pdf_bytes = b""
            if isinstance(b64, str) and b64.strip():
                try:
                    pdf_bytes = base64.standard_b64decode(b64.strip().encode("ascii"))
                except (ValueError, UnicodeEncodeError):
                    pdf_bytes = b""
            if pdf_bytes:
                meta = {k: v for k, v in data.items() if k not in ("pdf_base64", "mime_type")}
                fname = str(
                    meta.get("file_name")
                    or meta.get("fileName")
                    or meta.get("source_filename")
                    or ("consentimiento.pdf" if event == "contract_consent_pdf" else "orden_trabajo.pdf")
                ).strip()
                # Forzar consistencia: lo que recibe n8n como nombre del binario y en metadatos.
                meta["file_name"] = fname
                meta["fileName"] = fname
                meta["source_filename"] = fname
                ts = datetime.datetime.now().isoformat()
                form_data: dict[str, str] = {
                    "event": event,
                    "timestamp": ts,
                }
                for key, val in meta.items():
                    form_data[key] = _form_field_str(val)
                try:
                    logger.info(
                        "n8n %s (multipart): PDF %s (%s bytes) → %s",
                        event,
                        fname,
                        len(pdf_bytes),
                        url,
                    )
                    response = requests.post(
                        url,
                        files={
                            # Mismo nombre que el recibo / WhatsApp binary property «data»
                            "data": (fname, pdf_bytes, "application/pdf"),
                        },
                        data=form_data,
                        timeout=60,
                    )
                    if not _http_2xx(response.status_code):
                        logger.warning(
                            "n8n %s (multipart): HTTP %s desde %s — %s",
                            event,
                            response.status_code,
                            url,
                            (response.text or "")[:800],
                        )
                    return _http_2xx(response.status_code)
                except Exception:
                    logger.exception(
                        "n8n %s (multipart): error enviando PDF hacia %s",
                        event,
                        url,
                    )
                    return False

            logger.warning(
                "n8n %s: pdf_base64 vacío o PDF no decodificable; no se envía.",
                event,
            )
            return False

        payload = {
            "event": event,
            "data": data,
            "timestamp": datetime.datetime.now().isoformat(),
        }
        try:
            response = requests.post(url, json=payload, timeout=30)
            if not _http_2xx(response.status_code):
                logger.warning(
                    "n8n JSON %s: HTTP %s desde %s — %s",
                    event,
                    response.status_code,
                    url,
                    (response.text or "")[:800],
                )
            return _http_2xx(response.status_code)
        except Exception:
            logger.exception("n8n JSON event=%s hacia %s", event, url)
            return False
