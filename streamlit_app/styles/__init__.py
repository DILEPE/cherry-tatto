"""CSS y utilidades de estilo para vistas Streamlit (citas, etc.)."""

from streamlit_app.styles.inject import (
    build_citas_style_tag,
    inject_citas_tab_styles,
    inject_via_streamlit_lazy,
)

__all__ = [
    "build_citas_style_tag",
    "inject_citas_tab_styles",
    "inject_via_streamlit_lazy",
]
