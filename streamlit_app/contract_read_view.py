"""Vista URL para leer el contenido de un contrato firmado."""
from __future__ import annotations

import base64
import html as html_mod
import json
import re
from typing import Any

import streamlit as st

from streamlit_app import api_client


def _detail(payload: Any) -> str:
    if isinstance(payload, dict):
        return str(payload.get("detail", payload))
    return str(payload)


def _image_from_data_url(data_url: Any) -> bytes | None:
    if not isinstance(data_url, str):
        return None
    raw = data_url.strip()
    if not raw:
        return None
    if raw.startswith("data:image/") and "," in raw:
        try:
            return base64.b64decode(raw.split(",", 1)[1])
        except Exception:
            return None
    return None


def _contract_text_looks_like_html(s: str) -> bool:
    t = (s or "").lstrip()
    if not t.startswith("<"):
        return False
    return re.search(r"<[a-zA-Z][\w:-]*", t) is not None


def render_contract_read_view(contract_id: int) -> None:
    st.subheader("Contrato firmado")
    st.caption(f"Contrato #{contract_id}")
    if st.button("Volver al panel", key="ctrv_back"):
        st.query_params.clear()
        st.rerun()

    ok, code, data = api_client.get_contract(contract_id)
    if not ok or not isinstance(data, dict):
        st.error(f"No se pudo cargar contrato (HTTP {code}): {_detail(data)}")
        return

    st.caption(
        f"Cita: {data.get('appointment_id', '—')} · "
        f"Cliente: {data.get('customer_name', '—')} · "
        f"Servicio: {data.get('service_type', '—')}"
    )

    text = data.get("contract_text")
    if not text:
        st.warning("Este contrato no tiene `contract_text` guardado.")
        st.text_area("Contenido (fallback)", value=json.dumps(data, ensure_ascii=False, indent=2), height=320)
        return

    raw_text = str(text)
    st.markdown(
        """
        <style>
          .ctrv-contract-shell {
            background: linear-gradient(165deg, #fdfbf7 0%, #f3ede4 45%, #ebe4d8 100%);
            border: 1px solid #c9bfb0;
            border-radius: 14px;
            padding: 1.35rem 1.6rem;
            margin: 0.85rem 0 1.35rem 0;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.65), 0 4px 14px rgba(41, 37, 36, 0.08);
            max-height: min(72vh, 760px);
            overflow-y: auto;
            font-size: 0.98rem;
            line-height: 1.62;
            color: #1c1917;
          }
          .ctrv-contract-shell.ctrv-plain {
            white-space: pre-wrap;
            word-wrap: break-word;
            font-family: ui-sans-serif, system-ui, "Segoe UI", Roboto, sans-serif;
          }
          .ctrv-contract-html p { margin: 0.5em 0; }
          .ctrv-contract-html h1, .ctrv-contract-html h2, .ctrv-contract-html h3 {
            color: #1c1917;
            margin-top: 0.75em;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.caption("Contenido del contrato firmado")
    if _contract_text_looks_like_html(raw_text):
        st.markdown(
            f'<div class="ctrv-contract-shell ctrv-contract-html">{raw_text}</div>',
            unsafe_allow_html=True,
        )
    else:
        body = html_mod.escape(raw_text).replace("\n", "<br>\n")
        st.markdown(
            f'<div class="ctrv-contract-shell ctrv-plain">{body}</div>',
            unsafe_allow_html=True,
        )

    st.markdown("### Firmas")
    c1, c2, c3 = st.columns(3)
    sig_client = _image_from_data_url(data.get("client_signature"))
    sig_tutor = _image_from_data_url(data.get("tutor_signature"))
    sig_artist = _image_from_data_url(data.get("artist_signature"))

    with c1:
        st.caption("Cliente")
        if sig_client:
            st.image(sig_client, use_container_width=True)
        else:
            st.info("Sin firma de cliente en formato imagen.")
    with c2:
        st.caption("Tutor")
        if sig_tutor:
            st.image(sig_tutor, use_container_width=True)
        else:
            st.info("Sin firma de tutor en formato imagen.")
    with c3:
        st.caption("Tatuador/Perforador")
        if sig_artist:
            st.image(sig_artist, use_container_width=True)
        else:
            st.info("Sin firma de artista en formato imagen.")

    if bool(data.get("is_minor")):
        st.markdown("### Documento del tutor (menor de edad)")
        d1, d2 = st.columns(2)
        doc_front = _image_from_data_url(data.get("tutor_document_front"))
        doc_back = _image_from_data_url(data.get("tutor_document_back"))
        with d1:
            st.caption("Anverso")
            if doc_front:
                st.image(doc_front, use_container_width=True)
            else:
                st.info("Sin imagen de anverso.")
        with d2:
            st.caption("Reverso")
            if doc_back:
                st.image(doc_back, use_container_width=True)
            else:
                st.info("Sin imagen de reverso.")

