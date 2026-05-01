from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class N8nHealthResponse(BaseModel):
    """Salida de GET /health/n8n."""

    level: Literal["success", "warn", "error"] = Field(
        ...,
        description="success: upstream HTTP 200; warn: alcanzable pero distinto de 200; error: fallo.",
    )
    message: str = Field(..., description="Detalle para operadores.")
    upstream_http: Optional[int] = Field(
        None,
        description="HTTP devuelto por el GET (N8N_STATUS_URL si está definida, si no GET a N8N_WEBHOOK_URL).",
    )
    url_configured: bool = Field(
        ...,
        description="True si existe N8N_STATUS_URL o N8N_WEBHOOK_URL.",
    )
