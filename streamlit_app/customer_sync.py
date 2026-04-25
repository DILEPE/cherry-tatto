"""Reusable customer upsert logic for Streamlit and API consumers."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

from streamlit_app import api_client


def _detail(payload: Any) -> str:
    if isinstance(payload, dict):
        return str(payload.get("detail", payload))
    return str(payload)


def sync_customer(customer_payload: Dict[str, Any], document_number: str) -> Tuple[bool, str, Optional[int]]:
    """
    GET by document_number; if a row exists → PUT; else → POST.
    Returns (ok, message, customer_id).
    """
    doc = (document_number or customer_payload.get("document_number") or "").strip()
    if not doc:
        return False, "document_number is required", None

    ok, code, data = api_client.get_customers(limit=5, offset=0, document_number=doc)
    if not ok:
        return False, f"GET customers failed HTTP {code}: {_detail(data)}", None

    items = (data or {}).get("items") or []
    if items:
        cid = int(items[0]["id"])
        ok2, code2, data2 = api_client.put_customer(cid, customer_payload)
        if ok2:
            return True, "Cliente actualizado", cid
        return False, f"PUT customer failed HTTP {code2}: {_detail(data2)}", None

    ok3, code3, data3 = api_client.post_customer(customer_payload)
    if ok3 and isinstance(data3, dict) and data3.get("id") is not None:
        return True, "Cliente creado", int(data3["id"])
    return False, f"POST customer failed HTTP {code3}: {_detail(data3)}", None


def fetch_customer_by_document(document_number: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    doc = (document_number or "").strip()
    if not doc:
        return False, "Ingresa un número de documento", None
    ok, code, data = api_client.get_customers(limit=1, offset=0, document_number=doc)
    if not ok:
        return False, f"HTTP {code}: {_detail(data)}", None
    items = (data or {}).get("items") or []
    if not items:
        return True, "not_found", None
    return True, "ok", items[0]


def parse_social_media_json(raw: str) -> Optional[Dict[str, Any]]:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        val = json.loads(raw)
        return val if isinstance(val, dict) else None
    except json.JSONDecodeError:
        return None
