"""Vista URL para leer el contenido de un contrato firmado."""
from __future__ import annotations

import base64
import json
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

    st.text_area("Contenido del contrato", value=str(text), height=420)

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

