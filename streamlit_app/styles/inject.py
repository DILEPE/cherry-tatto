"""Inyección de estilos del tab Citas desde parciales CSS en disco."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import streamlit as st_module

_CSS_ORDER = (
    "_tokens.css",
    "_pills.css",
    "_calendar.css",
    "_flags.css",
    "_legend.css",
    "_appointment_search.css",
    "_appointment_payments.css",
)


def _styles_directory() -> Path:
    return Path(__file__).resolve().parent


def build_citas_style_tag() -> str:
    chunks: list[str] = []
    d = _styles_directory()
    for name in _CSS_ORDER:
        p = d / name
        chunks.append(p.read_text(encoding="utf-8"))
    return "<style>\n" + "\n".join(chunks) + "\n</style>"


def inject_citas_tab_styles(streamlit_module: object) -> None:
    inject = getattr(streamlit_module, "markdown", None)
    if inject is None:
        raise TypeError("inject_citas_tab_styles requiere el módulo streamlit.")
    inject(build_citas_style_tag(), unsafe_allow_html=True)


def inject_via_streamlit_lazy() -> None:
    """Convenience: mismo patrón que el resto de citas_tab (`import streamlit as st`)."""
    import streamlit as st_runtime

    inject_citas_tab_styles(st_runtime)

