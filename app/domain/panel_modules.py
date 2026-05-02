"""Módulos del panel operativo asignables a usuarios (no administradores)."""
from __future__ import annotations

from typing import Final

# Claves internas; la pestaña "Gestión de usuarios" solo la ven administradores (no se asigna aquí).
ASSIGNABLE_PANEL_MODULE_KEYS: Final[tuple[str, ...]] = (
    "citas",
    "clientes",
    "contratos",
    "encuestas",
    "reporte",
)

ASSIGNABLE_PANEL_MODULE_KEYS_SET: Final[frozenset[str]] = frozenset(ASSIGNABLE_PANEL_MODULE_KEYS)

PANEL_MODULE_LABEL_ES: Final[dict[str, str]] = {
    "citas": "Gestión citas",
    "clientes": "Gestión de clientes",
    "contratos": "Gestión contratos",
    "encuestas": "Gestión encuesta",
    "reporte": "Reporte",
}
