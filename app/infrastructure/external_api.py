from __future__ import annotations

import base64
import datetime
import json
from typing import Optional

import requests


def _form_field_str(val: object) -> str:
    if val is None:
        return ""
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False)
    return str(val)


class NotificationService:
    """Servicio para comunicarse con webhooks de n8n.

    Los recibos PDF (`payment_receipt_pdf`) pueden ir a un webhook dedicado
    (`receipt_webhook_url`); el resto de eventos usan `webhook_url`.

    Los recibos se envían como **multipart/form-data**: archivo binario en el campo **`data`**
    + campos de texto con los metadatos (nombre, teléfono, montos, etc.).
    Si no hay PDF válido en `pdf_base64`, se usa JSON como antes.
    """

    def __init__(
        self,
        webhook_url: Optional[str],
        receipt_webhook_url: Optional[str] = None,
    ):
        self.webhook_url = (webhook_url or "").strip() or None
        self.receipt_webhook_url = (receipt_webhook_url or "").strip() or None

    def _resolve_url(self, event: str) -> Optional[str]:
        if event == "payment_receipt_pdf":
            return self.receipt_webhook_url or self.webhook_url
        return self.webhook_url

    def notify(self, event: str, data: dict[str, object]) -> bool:
        url = self._resolve_url(event)
        if not url:
            return False

        if event == "payment_receipt_pdf":
            b64 = data.get("pdf_base64")
            if isinstance(b64, str) and b64.strip():
                try:
                    pdf_bytes = base64.standard_b64decode(b64.strip().encode("ascii"))
                except (ValueError, UnicodeEncodeError):
                    pdf_bytes = b""
                if pdf_bytes:
                    meta = {k: v for k, v in data.items() if k not in ("pdf_base64", "mime_type")}
                    fname = str(meta.get("file_name") or "recibo.pdf")
                    ts = datetime.datetime.now().isoformat()
                    form_data: dict[str, str] = {
                        "event": event,
                        "timestamp": ts,
                    }
                    for key, val in meta.items():
                        form_data[key] = _form_field_str(val)
                    try:
                        response = requests.post(
                            url,
                            files={
                                # Nombre coherente con nodos n8n que esperan binary property `data`
                                "data": (fname, pdf_bytes, "application/pdf"),
                            },
                            data=form_data,
                            timeout=60,
                        )
                        return response.status_code == 200
                    except Exception as e:
                        print(f"Error enviando recibo PDF (multipart) a n8n: {e}")
                        return False

        payload = {
            "event": event,
            "data": data,
            "timestamp": datetime.datetime.now().isoformat(),
        }
        try:
            response = requests.post(url, json=payload, timeout=30)
            return response.status_code == 200
        except Exception as e:
            print(f"Error enviando a n8n: {e}")
            return False