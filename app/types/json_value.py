"""Valor JSON (árbol) para serialización y esquemas; evita `Any` en contenedores."""
from __future__ import annotations

from typing import TypeAlias

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
