"""
Sondeo HTTP hacia n8n (GET; no ejecuta el flujo de negocio del webhook de notificación).

Preferencia en .env:
1. N8N_STATUS_URL — endpoint dedicado al status (recomendado), p. ej. webhook-test/.../status
2. Si no hay, N8N_WEBHOOK_URL — mismo criterio que antes (GET sobre la URL del webhook)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal, Optional, Tuple

import requests

Level = Literal["success", "warn", "error"]


@dataclass(slots=True)
class N8nProbeResult:
    level: Level
    message: str
    upstream_http: Optional[int]
    upstream_json: Optional[dict[str, Any]] = None


def _parse_upstream_json(r: requests.Response) -> Optional[dict[str, Any]]:
    try:
        if not r.content:
            return None
        data = r.json()
        return data if isinstance(data, dict) else None
    except ValueError:
        return None


def n8n_echo_fields_from_upstream(parsed: Optional[dict[str, Any]]) -> dict[str, Optional[str]]:
    """Extrae del JSON de n8n las claves esperadas por GET /health/n8n."""
    if not parsed:
        return {"status": None, "service": None, "check": None, "version": None}

    def pick(key: str) -> Optional[str]:
        v = parsed.get(key)
        if v is None:
            return None
        return str(v)

    return {
        "status": pick("status"),
        "service": pick("service"),
        "check": pick("check"),
        "version": pick("version"),
    }


def _resolve_n8n_probe_url_from_env() -> Tuple[Optional[str], Literal["status", "webhook"]]:
    status = (os.getenv("N8N_STATUS_URL") or "").strip().rstrip("/")
    if status:
        return status, "status"
    webhook = (os.getenv("N8N_WEBHOOK_URL") or "").strip().rstrip("/")
    if webhook:
        return webhook, "webhook"
    return None, "webhook"


def probe_n8n_from_env(timeout: float = 12.0) -> N8nProbeResult:
    url, source = _resolve_n8n_probe_url_from_env()
    if not url:
        return N8nProbeResult(
            level="error",
            message=(
                "Define N8N_STATUS_URL (endpoint de status en n8n) o N8N_WEBHOOK_URL en .env."
            ),
            upstream_http=None,
            upstream_json=None,
        )
    try:
        r = requests.get(url, timeout=timeout, allow_redirects=True)
    except requests.RequestException as e:
        return N8nProbeResult(level="error", message=str(e), upstream_http=None, upstream_json=None)
    parsed = _parse_upstream_json(r)
    code = r.status_code
    if code >= 500:
        return N8nProbeResult(
            level="error",
            message=f"El servidor remoto respondió con error HTTP {code}.",
            upstream_http=code,
            upstream_json=parsed,
        )
    if code == 200:
        via = "endpoint de status" if source == "status" else "webhook (GET de prueba)"
        return N8nProbeResult(
            level="success",
            message=f"n8n alcanzable (HTTP 200) vía {via}.",
            upstream_http=code,
            upstream_json=parsed,
        )
    if source == "status":
        return N8nProbeResult(
            level="warn",
            message=(
                f"Endpoint de status alcanzable pero respondió HTTP {code} (se esperaba 200)."
            ),
            upstream_http=code,
            upstream_json=parsed,
        )
    return N8nProbeResult(
        level="warn",
        message=(
            f"Servidor alcanzable, respuesta HTTP {code} (distinta de 200). "
            "En webhooks suele ser normal con GET."
        ),
        upstream_http=code,
        upstream_json=parsed,
    )


def probe_url_configured_from_env() -> bool:
    return bool(
        (os.getenv("N8N_STATUS_URL") or "").strip()
        or (os.getenv("N8N_WEBHOOK_URL") or "").strip()
    )


def probe_n8n_webhook_from_env(timeout: float = 12.0) -> N8nProbeResult:
    """Alias retrocompatible; usa N8N_STATUS_URL si existe."""
    return probe_n8n_from_env(timeout=timeout)
