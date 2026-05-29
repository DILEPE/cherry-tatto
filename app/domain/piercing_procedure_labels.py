"""Catálogo y resolución de tipos de perforación (encuesta / consentimientos / reportes)."""

from __future__ import annotations

import json
import unicodedata
from typing import Optional

# Opciones oficiales (pregunta encuesta id 3 / procedure_consent_documents).
PIERCING_TYPE_OPTIONS: tuple[str, ...] = (
    "Helix",
    "Lobulos",
    "Expansion Lobulos",
    "Nostril",
    "Surface",
    "Microdermal",
    "Septum",
    "Labio",
    "Ombligo",
    "Pezon",
    "Ceja",
    "Conch",
    "Industrial",
    "Upper Lobe",
    "Tragus",
    "Lengua",
    "Cristina",
    "Daith",
    "Rook",
    "Antihelix",
    "Contrahelix",
    "Flat",
)

# Etiqueta en reportes (legible; clave = texto canónico de encuesta/BD).
PIERCING_TYPE_DISPLAY_ES: dict[str, str] = {
    "Helix": "Helix",
    "Lobulos": "Lóbulo",
    "Expansion Lobulos": "Expansión lóbulos",
    "Nostril": "Nostril",
    "Surface": "Surface",
    "Microdermal": "Microdermal",
    "Septum": "Septum",
    "Labio": "Labio",
    "Ombligo": "Ombligo",
    "Pezon": "Pezón",
    "Ceja": "Ceja",
    "Conch": "Conch",
    "Industrial": "Industrial",
    "Upper Lobe": "Upper lobe",
    "Tragus": "Tragus",
    "Lengua": "Lengua",
    "Cristina": "Cristina",
    "Daith": "Daith",
    "Rook": "Rook",
    "Antihelix": "Antihelix",
    "Contrahelix": "Contrahelix",
    "Flat": "Flat",
}

# Alias frecuentes (sin tildes / errores) → canónico de encuesta.
_PIERCING_TYPE_ALIASES: dict[str, str] = {
    "helix": "Helix",
    "hellix": "Helix",
    "lobulo": "Lobulos",
    "lobulos": "Lobulos",
    "lobulo superior": "Upper Lobe",
    "upper lobe": "Upper Lobe",
    "expansion lobulos": "Expansion Lobulos",
    "expansion lobulo": "Expansion Lobulos",
    "nostril": "Nostril",
    "nostry": "Nostril",
    "nariz": "Nostril",
    "surface": "Surface",
    "microdermal": "Microdermal",
    "septum": "Septum",
    "labio": "Labio",
    "ombligo": "Ombligo",
    "pezon": "Pezon",
    "ceja": "Ceja",
    "conch": "Conch",
    "industrial": "Industrial",
    "tragus": "Tragus",
    "lengua": "Lengua",
    "cristina": "Cristina",
    "daith": "Daith",
    "rook": "Rook",
    "antihelix": "Antihelix",
    "contrahelix": "Contrahelix",
    "flat": "Flat",
}


def _ascii_fold(s: str) -> str:
    n = unicodedata.normalize("NFKD", s)
    return "".join(c for c in n if not unicodedata.combining(c)).lower().strip()


def expand_procedure_answer_candidates(raw: str) -> list[str]:
    """Opción única o elementos de lista JSON (checkbox) candidatos a etiqueta."""
    s = (raw or "").strip()
    if not s:
        return []
    out: list[str] = [s]
    try:
        parsed = json.loads(s)
        if isinstance(parsed, list):
            for x in parsed:
                sx = str(x).strip()
                if sx:
                    out.append(sx)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return out


def build_piercing_type_index(*, consent_labels: Optional[list[str]] = None) -> dict[str, str]:
    """Índice clave normalizada (ASCII minúsculas) → etiqueta canónica de encuesta."""
    index: dict[str, str] = {}
    for opt in PIERCING_TYPE_OPTIONS:
        index[_ascii_fold(opt)] = opt
    for alias, canonical in _PIERCING_TYPE_ALIASES.items():
        index[_ascii_fold(alias)] = canonical
    for lbl in consent_labels or []:
        t = str(lbl or "").strip()
        if t:
            index[_ascii_fold(t)] = t
    return index


def resolve_piercing_type_canonical(
    raw: Optional[str],
    index: dict[str, str],
) -> Optional[str]:
    """Devuelve Helix, Lobulos, Nostril… si el texto encaja con el catálogo."""
    for cand in expand_procedure_answer_candidates(raw or ""):
        piece = cand.strip()
        if not piece:
            continue
        key = _ascii_fold(piece)
        if key in index:
            return index[key]
        # Coincidencia por inclusión (p. ej. detalle «[Piercing] helix oreja»).
        for norm_key, canonical in index.items():
            if len(norm_key) >= 4 and (norm_key in key or key in norm_key):
                return canonical
    return None


def piercing_type_display_label(canonical: str) -> str:
    """Texto para UI/reporte a partir del valor canónico."""
    c = str(canonical or "").strip()
    if not c:
        return "—"
    return PIERCING_TYPE_DISPLAY_ES.get(c, c)


def infer_piercing_type_from_detail(detail: Optional[str], index: dict[str, str]) -> Optional[str]:
    """Intenta detectar el tipo en el campo detalle de la cita."""
    det = str(detail or "").strip()
    if not det:
        return None
    return resolve_piercing_type_canonical(det, index)


__all__ = [
    "PIERCING_TYPE_DISPLAY_ES",
    "PIERCING_TYPE_OPTIONS",
    "build_piercing_type_index",
    "expand_procedure_answer_candidates",
    "infer_piercing_type_from_detail",
    "piercing_type_display_label",
    "resolve_piercing_type_canonical",
]
