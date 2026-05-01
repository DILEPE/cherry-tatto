"""Utilidades para tipos de pregunta de encuesta y opciones JSON."""
from __future__ import annotations

import json
from typing import Any, Optional

# Tipos que requieren lista `options` (radio, casillas, desplegable).
QUESTION_TYPES_NEEDING_OPTIONS = frozenset({"radio", "checkbox", "select"})

# Tipos con respuestas que suelen representarse bien en gráficas de barras (conteos / distribución).
QUESTION_TYPES_CHARTABLE = frozenset(
    {"rating_1_5", "yes_no", "number", "radio", "select", "checkbox"}
)

_QUESTION_LABELS_ES: dict[str, str] = {
    "rating_1_5": "Escala 1–5",
    "yes_no": "Sí / No",
    "text": "Texto libre (histórico)",
    "textarea": "Área de texto (varias líneas)",
    "text_short": "Texto en una línea",
    "number": "Numérico",
    "radio": "Una opción (radio)",
    "checkbox": "Varias opciones (casillas)",
    "select": "Lista desplegable",
}


def question_type_label_es(qt: str) -> str:
    return _QUESTION_LABELS_ES.get(qt, qt)


def question_type_supports_distribution_chart(question_type: str) -> bool:
    """Indica si el tipo de pregunta encaja en un resumen por barras cuando hay datos agregados."""
    return str(question_type or "").strip() in QUESTION_TYPES_CHARTABLE


def parse_options_json(raw: Any) -> Optional[list[str]]:
    if raw is None:
        return None
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return None
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [str(x).strip() for x in data if str(x).strip()]
        except json.JSONDecodeError:
            return None
    return None
