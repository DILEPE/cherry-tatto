"""Texto corto desde cuerpo de error HTTP (JSON o string)."""

from __future__ import annotations

from typing import Any


def format_http_error_detail(payload: Any) -> str:
    if isinstance(payload, dict):
        return str(payload.get("detail", payload))
    return str(payload)


__all__ = ["format_http_error_detail"]
