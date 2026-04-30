
"""
Valores válidos para la columna ENUM `service_type` en MySQL.

Define en `.env` la lista separada por comas, **exactamente** como en el ENUM:

  SERVICE_TYPE_ENUM_VALUES=tattoo,piercing,other

Si no existe la variable, se usan por defecto literales en inglés habituales en ENUM.
"""
from __future__ import annotations

import os
from typing import Tuple


def configured_service_types() -> Tuple[str, ...]:
    raw = os.getenv("SERVICE_TYPE_ENUM_VALUES", "").strip()
    if raw:
        return tuple(x.strip() for x in raw.split(",") if x.strip())
    return ("tattoo", "piercing", "other")


def resolve_service_type(user_text: str) -> str:
    """
    Convierte texto libre (o etiqueta de formulario) al literal ENUM que exista en la BD.
    """
    labels = configured_service_types()
    if not labels:
        return ""
    t = (user_text or "").strip().lower()
    if not t:
        return labels[0]

    for label in labels:
        if label.lower() == t:
            return label

    def pick(predicate) -> str | None:
        for label in labels:
            if predicate(label):
                return label
        return None

    if any(k in t for k in ("tatuaje", "tattoo", "tinta", "cover", "boceto", "retoque")):
        found = pick(lambda L: "tatu" in L.lower() or "tattoo" in L.lower())
        if found:
            return found

    if any(k in t for k in ("piercing", "arete", "barbell", "dilatación", "dilatacion")):
        found = pick(lambda L: "pierc" in L.lower())
        if found:
            return found

    if any(
        k in t
        for k in (
            "otro",
            "other",
            "consulta",
            "sesión",
            "sesion",
            "limpieza",
            "mantenimiento",
            "curación",
            "curacion",
        )
    ):
        found = pick(lambda L: "otr" in L.lower() or "other" in L.lower() or "consult" in L.lower())
        if found:
            return found

    return labels[0]
