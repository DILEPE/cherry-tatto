"""Editor enriquecido opcional (Quill) para plantillas y contrato en firma."""
from __future__ import annotations

import streamlit as st

try:
    from streamlit_quill import st_quill

    HAS_QUILL = True
except Exception:  # pragma: no cover
    st_quill = None  # type: ignore[misc, assignment]
    HAS_QUILL = False

CONTRACT_PLACEHOLDERS_CAPTION = (
    "Variables admitidas en el texto: "
    "`{{nombres}}`, `{{identificacion}}`, `{{numero_documento}}`, `{{fecha_expedicion}}`, "
    "`{{nombre_tutor}}`, `{{identificacion_tutor}}`, `{{numero_documento_tutor}}`, "
    "`{{fecha_expedicion_tutor}}`."
)


def contract_rich_editor(
    *,
    label: str,
    value: str,
    key: str,
    show_placeholders: bool = True,
) -> str:
    """Devuelve HTML (si Quill está instalado) o texto plano."""
    if show_placeholders:
        st.caption(CONTRACT_PLACEHOLDERS_CAPTION)
    v = value if value is not None else ""
    if HAS_QUILL and st_quill is not None:
        st.markdown(
            f'<p style="margin:0 0 0.35rem 0;font-weight:600;color:#374151">{label}</p>',
            unsafe_allow_html=True,
        )
        out = st_quill(
            value=v,
            placeholder="Redacta aquí…",
            html=True,
            key=key,
        )
        return (out or "").strip()
    st.markdown(
        f'<p style="margin:0 0 0.35rem 0;font-weight:600;color:#374151">{label}</p>',
        unsafe_allow_html=True,
    )
    st.caption("Instala `streamlit-quill` para tamaño de letra, negritas y encabezados en el editor.")
    return st.text_area(label, value=v, height=320, label_visibility="collapsed", key=key).strip()
