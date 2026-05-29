"""Duración de la sesión activa del panel por usuario."""
from __future__ import annotations

import time

PANEL_SESSION_LIFETIME_MINUTES = 60
PANEL_SESSION_TTL_SECONDS = PANEL_SESSION_LIFETIME_MINUTES * 60


def panel_session_expires_at_epoch(from_ts: float | None = None) -> float:
    """Instante Unix (segundos) en que expira la sesión."""
    base = float(from_ts if from_ts is not None else time.time())
    return base + float(PANEL_SESSION_TTL_SECONDS)


def panel_session_is_expired(expires_at: float | None) -> bool:
    if expires_at is None:
        return True
    try:
        return time.time() >= float(expires_at)
    except (TypeError, ValueError):
        return True
