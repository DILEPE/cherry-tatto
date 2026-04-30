"""Rutas de health (servicio y dependencias externas)."""
from __future__ import annotations

import asyncio

from litestar import Controller, Response, get

from app.infrastructure.n8n_health import probe_n8n_from_env, probe_url_configured_from_env
from app.schemas.health import N8nHealthResponse


class HealthController(Controller):
    path = "/health"

    @get("/n8n")
    async def n8n_upstream(self) -> Response:
        """
        Comprueba conectividad hacia la URL configurada en N8N_WEBHOOK_URL (GET sobre el webhook).
        Responde 200 si hay sondeo exitoso pero el upstream puede estar en nivel warn;
        503 si no hay URL, error de red o HTTP ≥ 500 desde n8n.
        """
        result = await asyncio.to_thread(probe_n8n_from_env)
        body = N8nHealthResponse(
            level=result.level,
            message=result.message,
            upstream_http=result.upstream_http,
            url_configured=probe_url_configured_from_env(),
        )
        status = 503 if result.level == "error" else 200
        return Response(content=body, status_code=status)
