"""Vista URL dedicada para firma de contrato desde una cita."""
from __future__ import annotations

import base64
import io
import sys
from typing import Any, Optional

import streamlit as st

from streamlit_app import api_client

try:
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None  # type: ignore[assignment]

try:
    from streamlit_drawable_canvas import st_canvas
except Exception:  # pragma: no cover
    st_canvas = None  # type: ignore[assignment]


def _detail(payload: Any) -> str:
    if isinstance(payload, dict):
        return str(payload.get("detail", payload))
    return str(payload)


def _render_contract_text(template_content: str, customer: dict[str, Any]) -> str:
    is_minor = bool(customer.get("is_minor"))
    replacements = {
        "{{nombres}}": f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip(),
        "{{identificacion}}": str(customer.get("document_type") or ""),
        "{{numero_documento}}": str(customer.get("document_number") or ""),
        "{{fecha_expedicion}}": str(customer.get("document_issue_date") or ""),
        "{{nombre_tutor}}": str(customer.get("guardian_name") or "") if is_minor else "",
        "{{identificacion_tutor}}": str(customer.get("guardian_document_type") or "") if is_minor else "",
        "{{numero_documento_tutor}}": str(customer.get("guardian_document_number") or "") if is_minor else "",
        "{{fecha_expedicion_tutor}}": str(customer.get("guardian_document_issue_date") or "") if is_minor else "",
    }
    out = template_content
    for k, v in replacements.items():
        out = out.replace(k, v)
    return out


def _image_file_to_base64(uploaded_file) -> Optional[str]:
    if uploaded_file is None:
        return None
    data = uploaded_file.read()
    if not data:
        return None
    return "data:image/jpeg;base64," + base64.b64encode(data).decode("utf-8")


def _signature_pad_b64(label: str, key_prefix: str) -> Optional[str]:
    st.caption(label)
    canvas_impl = st_canvas
    if canvas_impl is None:
        try:
            # Reintento dinámico por si el paquete se instaló con la app abierta.
            from streamlit_drawable_canvas import st_canvas as _st_canvas  # type: ignore

            canvas_impl = _st_canvas
        except Exception:
            canvas_impl = None

    if canvas_impl is None or Image is None:
        st.warning(
            "No se pudo cargar streamlit-drawable-canvas en este runtime. "
            f"Python activo: `{sys.executable}`. "
            "Usando fallback de texto."
        )
        st.caption(
            "Si acabas de instalar el paquete, reinicia Streamlit. "
            f"Comando recomendado: `{sys.executable} -m pip install streamlit-drawable-canvas`"
        )
        fallback = st.text_input(f"{label} (fallback texto)", key=f"{key_prefix}_fallback")
        return fallback.strip() or None

    canvas = canvas_impl(
        stroke_width=3,
        stroke_color="#222222",
        background_color="#f8f8f3",
        height=180,
        width=620,
        drawing_mode="freedraw",
        key=f"{key_prefix}_canvas",
    )
    if canvas.image_data is None:
        return None
    # Convertir numpy RGBA a PNG base64
    image = Image.fromarray((canvas.image_data).astype("uint8"), mode="RGBA")
    bytes_buf = io.BytesIO()
    image.save(bytes_buf, format="PNG")
    raw = bytes_buf.getvalue()
    # Si prácticamente vacía, no guardar
    if len(raw) < 1500:
        return None
    return "data:image/png;base64," + base64.b64encode(raw).decode("utf-8")


def render_contract_signing_view(appointment_id: int) -> None:
    st.subheader("Firma digital de contrato")
    st.caption(f"Cita #{appointment_id}")
    if st.button("Volver al panel principal", key="ctsig_back"):
        st.query_params.clear()
        st.rerun()

    ok_a, code_a, appts = api_client.get_appointments()
    if not ok_a or not isinstance(appts, list):
        st.error(f"No se pudo cargar citas (HTTP {code_a}): {_detail(appts)}")
        return

    appt = next((a for a in appts if int(a.get("id", 0)) == int(appointment_id)), None)
    if not appt:
        st.error("Cita no encontrada.")
        return
    customer_id = appt.get("customer_id")
    if not customer_id:
        st.error("La cita no tiene cliente vinculado.")
        return

    ok_c, code_c, customer = api_client.get_customer(int(customer_id))
    if not ok_c or not isinstance(customer, dict):
        st.error(f"No se pudo cargar cliente (HTTP {code_c}): {_detail(customer)}")
        return

    ok_t, code_t, templates = api_client.get_templates(True)
    if not ok_t or not isinstance(templates, list):
        st.error(f"No se pudo cargar plantilla activa (HTTP {code_t}): {_detail(templates)}")
        return
    if not templates:
        st.error("No hay plantilla activa. Activa una versión desde Administrador de contratos.")
        return

    template_options = {int(t["id"]): f"{t.get('name')} · v{t.get('version')}" for t in templates}
    default_tid = list(template_options.keys())[0]
    selected_tid = st.selectbox(
        "Plantilla activa a usar",
        options=list(template_options.keys()),
        index=0,
        format_func=lambda x: template_options[x],
        key="ctsig_template",
    )
    selected_tid = int(selected_tid or default_tid)
    ok_tpl, code_tpl, tpl = api_client.get_template(selected_tid)
    if not ok_tpl or not isinstance(tpl, dict):
        st.error(f"No se pudo abrir la plantilla (HTTP {code_tpl}): {_detail(tpl)}")
        return

    contract_text = _render_contract_text(str(tpl.get("content", "")), customer)
    st.markdown(
        """
        <style>
        .soft-contract-read {
            background: #f5f3ee;
            color: #2d2d2d;
            border: 1px solid #d7d2c7;
            border-radius: 10px;
            padding: 12px;
            margin-bottom: 8px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div class="soft-contract-read">Texto del contrato para lectura</div>', unsafe_allow_html=True)
    editable_text = st.text_area("Contrato (editable)", value=contract_text, height=320, key="ctsig_text")

    is_minor = bool(customer.get("is_minor"))
    st.caption(
        f"Cliente: {customer.get('first_name','')} {customer.get('last_name','')} · "
        f"{customer.get('document_type','')} {customer.get('document_number','')}"
    )
    if is_minor:
        st.info("Cliente menor de edad: se requiere documento del tutor (anverso/reverso) y firma del tutor.")

    client_signature = _signature_pad_b64("Firma del cliente", "ctsig_client")
    tutor_signature = None
    tutor_doc_front = None
    tutor_doc_back = None
    if is_minor:
        tutor_signature = _signature_pad_b64("Firma del tutor", "ctsig_tutor")
        tutor_doc_front = _image_file_to_base64(
            st.camera_input("Documento tutor - anverso", key="ctsig_tutor_front")
        )
        tutor_doc_back = _image_file_to_base64(
            st.camera_input("Documento tutor - reverso", key="ctsig_tutor_back")
        )

    artist_signature = _signature_pad_b64("Firma del tatuador/perforador", "ctsig_artist")

    if st.button("Guardar contrato firmado", type="primary", use_container_width=True, key="ctsig_save"):
        if not client_signature:
            st.error("La firma del cliente es obligatoria.")
            return
        if not artist_signature:
            st.error("La firma del tatuador/perforador es obligatoria.")
            return
        if is_minor:
            if not tutor_signature:
                st.error("La firma del tutor es obligatoria para menores.")
                return
            if not tutor_doc_front or not tutor_doc_back:
                st.error("Debes capturar anverso y reverso del documento del tutor.")
                return

        payload = {
            "appointment_id": int(appointment_id),
            "is_minor": is_minor,
            "health_data": {"source": "contract_signing_view", "template_id": selected_tid},
            "signature": client_signature,
            "tutor_signature": tutor_signature,
            "artist_signature": artist_signature,
            "tutor_document_front": tutor_doc_front,
            "tutor_document_back": tutor_doc_back,
            "contract_text": editable_text,
            "template_id": selected_tid,
        }
        ok_s, code_s, data_s = api_client.post_contract(payload)
        if ok_s:
            st.success("Contrato firmado y guardado correctamente.")
        else:
            st.error(f"No se pudo guardar (HTTP {code_s}): {_detail(data_s)}")

