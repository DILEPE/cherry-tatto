"""Vista URL dedicada para firma de contrato desde una cita (3 etapas: datos, firma, cuestionario)."""
from __future__ import annotations

import base64
import html as html_mod
import io
import sys
from datetime import date
from typing import Any, Optional

import json

import streamlit as st

from app.schemas.customer import CUSTOMER_BIRTH_PENDING, SOCIAL_MEDIA_MAX_LEN
from app.domain.contract_kinds import KIND_LABEL_ES, appointment_to_contract_kind, service_type_requires_contract
from streamlit_app import api_client
from streamlit_app.customer_sync import social_media_api_to_form_text, social_media_form_text_to_api
from streamlit_app.validation import (
    mobile_phone_co_10_error,
    optional_mobile_phone_co_10_error,
    social_media_text_error,
)
from streamlit_app.customers_management import (
    _clamp_date,
    _date_range_100y,
    _doc_type_index,
    _is_minor_by_birth_date,
    _parse_date,
    _validate_document_rules,
)

CONTRACT_NO_REFUND_NOTICE = (
    "Por favor, tenga en cuenta que no hay devolución de dinero por citas apartadas, tampoco por abonos. "
    "En caso de modificaciones de último momento en los diseños, su valor puede aumentar."
)

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


def _date_to_api(val: Any) -> Optional[str]:
    if val is None:
        return None
    if isinstance(val, str) and val:
        return val[:10]
    if isinstance(val, date):
        return val.isoformat()
    return None


def _put_payload_from_customer(c: dict[str, Any]) -> dict[str, Any]:
    """Cuerpo PUT alineado con CustomerUpdate / gestor de clientes."""
    sm = c.get("social_media")
    if isinstance(sm, dict):
        try:
            sm_out: Any = json.dumps(sm, ensure_ascii=False)[:SOCIAL_MEDIA_MAX_LEN]
        except (TypeError, ValueError):
            sm_out = None
    elif isinstance(sm, str) and sm.strip():
        sm_out = sm.strip()[:SOCIAL_MEDIA_MAX_LEN]
    else:
        sm_out = None
    return {
        "first_name": (c.get("first_name") or "").strip(),
        "last_name": (c.get("last_name") or "").strip(),
        "birth_date": _date_to_api(c.get("birth_date")) or "1990-01-01",
        "document_type": c.get("document_type") or "CC",
        "document_number": (c.get("document_number") or "").strip(),
        "document_issue_date": _date_to_api(c.get("document_issue_date")),
        "email": (c.get("email") or "").strip(),
        "phone_number": (c.get("phone_number") or "").strip(),
        "address": (c.get("address") or "").strip() or None,
        "nationality": (c.get("nationality") or "").strip() or None,
        "profession": (c.get("profession") or "").strip() or None,
        "social_media": sm_out,
        "emergency_contact_name": (c.get("emergency_contact_name") or "").strip() or None,
        "emergency_contact_phone": (c.get("emergency_contact_phone") or "").strip() or None,
        "is_minor": bool(c.get("is_minor")),
        "guardian_name": (c.get("guardian_name") or "").strip() or None,
        "guardian_document_type": c.get("guardian_document_type"),
        "guardian_document_number": (c.get("guardian_document_number") or "").strip() or None,
        "guardian_document_issue_date": _date_to_api(c.get("guardian_document_issue_date")),
    }


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


def _procedure_noun_es(appointment: dict[str, Any]) -> str:
    """Sustantivo del procedimiento según el tipo de cita (plantilla tattoo vs piercing)."""
    return "tatuaje" if appointment_to_contract_kind(appointment) == "tattoo" else "piercing"


def _guardian_authorization_paragraph_html(
    customer: dict[str, Any],
    appointment: dict[str, Any],
    *,
    tutor_name: str,
) -> str:
    """
    Párrafo legal de autorización del tutor (se anexa al contract_text guardado para menores;
    en pantalla va en un recuadro aparte, no dentro del HTML de la plantilla).
    """
    proc = html_mod.escape(_procedure_noun_es(appointment))
    nombre_cliente = html_mod.escape(
        f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip()
    )
    nt = tutor_name.strip()
    nombre_tutor = html_mod.escape(nt) if nt else "________________"
    return (
        f'<p style="margin:0;">'
        f"Autorizo en calidad de padre o madre, <strong>{nombre_tutor}</strong>, a mi hijo/a "
        f"<strong>{nombre_cliente}</strong> a realizarse el <strong>{proc}</strong> en el lugar del cuerpo que se ha "
        f"especificado en este documento bajo mi única responsabilidad.</p>"
    )


def _minor_guardian_declaration_panel_html(
    customer: dict[str, Any],
    appointment: dict[str, Any],
    *,
    tutor_name: str,
) -> str:
    """Panel tipo contrato (mismo estilo) con Cliente + declaración del tutor."""
    fn = f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip()
    dt = str(customer.get("document_type") or "")
    dn = str(customer.get("document_number") or "").strip()
    client_line = (
        f'<p style="margin:0 0 0.85rem 0;font-size:0.95rem;line-height:1.55;">'
        f"<strong>Cliente:</strong> "
        f"{html_mod.escape(fn)} · {html_mod.escape(dt)} {html_mod.escape(dn)}</p>"
    )
    auth = _guardian_authorization_paragraph_html(customer, appointment, tutor_name=tutor_name)
    return f'<div class="ctsig-declaration-alert">{client_line}{auth}</div>'


def _image_file_to_base64(uploaded_file) -> Optional[str]:
    if uploaded_file is None:
        return None
    data = uploaded_file.read()
    if not data:
        return None
    return "data:image/jpeg;base64," + base64.b64encode(data).decode("utf-8")


def _signature_pad_b64(
    label: str,
    key_prefix: str,
    *,
    canvas_width: int = 620,
    canvas_height: int = 180,
) -> Optional[str]:
    st.markdown(f"**{label}**")
    canvas_impl = st_canvas
    if canvas_impl is None:
        try:
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
        height=canvas_height,
        width=canvas_width,
        drawing_mode="freedraw",
        key=f"{key_prefix}_canvas",
    )
    if canvas.image_data is None:
        return None
    image = Image.fromarray((canvas.image_data).astype("uint8"), mode="RGBA")
    bytes_buf = io.BytesIO()
    image.save(bytes_buf, format="PNG")
    raw = bytes_buf.getvalue()
    if len(raw) < 1500:
        return None
    return "data:image/png;base64," + base64.b64encode(raw).decode("utf-8")


def _steps_progress(step: int) -> None:
    titles = ("Datos personales", "Firma del contrato", "Cuestionario")
    st.caption(f"Paso **{step}/3** — {titles[step - 1]}")


def _render_step1_personal(customer_id: int, customer: dict[str, Any]) -> None:
    st.markdown("#### Etapa 1 — Completar datos del cliente")
    st.caption(
        "Alineado con **Gestión de clientes**: revisa y completa lo que falte. "
        "Si la fecha de nacimiento indica **menor de edad**, deberás completar **datos del tutor en la etapa 2** antes de firmar."
    )
    min_date_100, max_date_today = _date_range_100y()
    ed = customer
    if _parse_date(ed.get("birth_date")) == CUSTOMER_BIRTH_PENDING:
        st.info(
            "Cliente registrado solo con agendamiento: **aún no hay fecha de nacimiento real**. "
            "Indica la fecha correcta aquí para detectar menor de edad y el tutor en la etapa 2."
        )

    a, b = st.columns(2)
    with a:
        st.text_input("Nombre *", value=str(ed.get("first_name") or ""), key="ctsig_s1_fn")
        st.text_input("Apellido *", value=str(ed.get("last_name") or ""), key="ctsig_s1_ln")
        bd = st.date_input(
            "Fecha de nacimiento *",
            value=_clamp_date(_parse_date(ed.get("birth_date")), min_date_100, max_date_today),
            min_value=min_date_100,
            max_value=max_date_today,
            key="ctsig_s1_bd",
            format="DD/MM/YYYY",
        )
        if _is_minor_by_birth_date(bd):
            st.warning(
                "**Menor de edad:** en la **etapa 2 (Firma)** deberás completar los datos del tutor o representante "
                "y la documentación requerida antes de guardar el contrato."
            )
        edt = st.selectbox(
            "Tipo de documento *",
            ["CC", "TI", "CE", "PAS"],
            index=_doc_type_index(ed.get("document_type")),
            format_func=lambda x: {"CC": "CC — Cédula", "TI": "TI — Tarjeta identidad", "CE": "CE — Extranjería", "PAS": "PAS — Pasaporte"}[x],
            key="ctsig_s1_dt",
        )
        st.text_input("Número de documento *", value=str(ed.get("document_number") or ""), key="ctsig_s1_dn")
        eddi_raw = ed.get("document_issue_date")
        st.checkbox(
            "Registrar fecha de expedición del documento del cliente",
            value=bool(eddi_raw),
            key="ctsig_s1_has_ddi",
        )
        st.date_input(
            "Fecha de expedición del documento del cliente",
            value=_clamp_date(_parse_date(eddi_raw), min_date_100, max_date_today) if eddi_raw else date(2015, 1, 1),
            min_value=min_date_100,
            max_value=max_date_today,
            key="ctsig_s1_ddi",
            format="DD/MM/YYYY",
        )
    with b:
        st.text_input("Correo *", value=str(ed.get("email") or ""), key="ctsig_s1_em")
        st.text_input(
            "Celular *",
            value=str(ed.get("phone_number") or ""),
            key="ctsig_s1_ph",
            help="10 dígitos (puedes escribir espacios o +57; se validan solo los dígitos).",
        )
        st.text_input(
            "Nacionalidad (recomendado)",
            value=str(ed.get("nationality") or ""),
            key="ctsig_s1_nat",
        )
        st.text_input(
            "Profesión (recomendado)",
            value=str(ed.get("profession") or ""),
            key="ctsig_s1_prof",
        )

    with st.expander("Contacto y redes", expanded=False):
        st.text_input("Dirección", value=str(ed.get("address") or ""), key="ctsig_s1_addr")
        st.text_area(
            "Redes sociales (recomendado)",
            value=social_media_api_to_form_text(ed.get("social_media")),
            height=70,
            key="ctsig_s1_sm",
            max_chars=SOCIAL_MEDIA_MAX_LEN,
            help=f"Texto plano, máximo {SOCIAL_MEDIA_MAX_LEN} caracteres (@, enlaces, etc.). No es JSON.",
        )

    with st.expander("Contacto de emergencia", expanded=False):
        st.text_input("Nombre contacto emergencia", value=str(ed.get("emergency_contact_name") or ""), key="ctsig_s1_ecn")
        st.text_input(
            "Celular contacto emergencia",
            value=str(ed.get("emergency_contact_phone") or ""),
            key="ctsig_s1_ecp",
            help="Si lo completas, deben ser 10 dígitos.",
        )

    st.info(
        "**Tutor / representante:** no se registran en esta etapa. "
        "Si aplica menor de edad, la **etapa 2** solicitará nombre, documento y capturas del tutor además de las firmas."
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Guardar y continuar a la firma", type="primary", use_container_width=True, key="ctsig_s1_next"):
            fn = (st.session_state.get("ctsig_s1_fn") or "").strip()
            ln = (st.session_state.get("ctsig_s1_ln") or "").strip()
            if len(fn) < 1 or len(ln) < 1:
                st.error("Nombre y apellido son obligatorios.")
                return
            bd_v = st.session_state.get("ctsig_s1_bd")
            if not isinstance(bd_v, date):
                bd_v = _parse_date(bd_v)
            if bd_v == CUSTOMER_BIRTH_PENDING:
                st.error(
                    "Indica la **fecha de nacimiento real** del cliente (no la fecha provisional del agendamiento)."
                )
                return
            expected_minor = _is_minor_by_birth_date(bd_v)
            dt = str(st.session_state.get("ctsig_s1_dt") or "CC")
            dn = (st.session_state.get("ctsig_s1_dn") or "").strip()
            if len(dn) < 5:
                st.error("Número de documento inválido.")
                return
            has_ddi = bool(st.session_state.get("ctsig_s1_has_ddi"))
            ddi_v = st.session_state.get("ctsig_s1_ddi")
            if not isinstance(ddi_v, date):
                ddi_v = _parse_date(ddi_v)
            doc_err = _validate_document_rules(
                birth_date=bd_v,
                document_type=dt,
                has_document_issue_date=has_ddi,
                document_issue_date=ddi_v,
            )
            if doc_err:
                st.error(doc_err)
                return
            em = (st.session_state.get("ctsig_s1_em") or "").strip()
            ph = (st.session_state.get("ctsig_s1_ph") or "").strip()
            if len(em) < 3:
                st.error("El correo es obligatorio (formato válido).")
                return
            ph_err = mobile_phone_co_10_error(ph)
            if ph_err:
                st.error(ph_err)
                return
            ecp = (st.session_state.get("ctsig_s1_ecp") or "").strip()
            ecp_err = optional_mobile_phone_co_10_error(ecp)
            if ecp_err:
                st.error(f"Contacto de emergencia: {ecp_err}")
                return
            sm_raw = st.session_state.get("ctsig_s1_sm") or ""
            sm_err = social_media_text_error(str(sm_raw))
            if sm_err:
                st.error(sm_err)
                return

            nat = (st.session_state.get("ctsig_s1_nat") or "").strip()
            prof = (st.session_state.get("ctsig_s1_prof") or "").strip()
            sm_for_api = social_media_form_text_to_api(str(sm_raw))
            soft_missing: list[str] = []
            if not nat:
                soft_missing.append("nacionalidad")
            if not prof:
                soft_missing.append("profesión")
            if not sm_for_api:
                soft_missing.append("redes sociales (texto)")
            if soft_missing:
                st.warning(
                    "**Datos recomendados pendientes:** "
                    + ", ".join(soft_missing)
                    + ". Puedes continuar; conviene completarlos para el expediente."
                )

            base = _put_payload_from_customer(customer)
            payload = {
                **base,
                "first_name": fn,
                "last_name": ln,
                "birth_date": bd_v.isoformat(),
                "document_type": dt,
                "document_number": dn,
                "document_issue_date": ddi_v.isoformat() if has_ddi else None,
                "email": em,
                "phone_number": ph,
                "nationality": nat or None,
                "profession": prof or None,
                "address": (st.session_state.get("ctsig_s1_addr") or "").strip() or None,
                "social_media": sm_for_api,
                "emergency_contact_name": (st.session_state.get("ctsig_s1_ecn") or "").strip() or None,
                "emergency_contact_phone": ecp or None,
                "is_minor": expected_minor,
            }
            ok, code, data = api_client.put_customer(customer_id, payload)
            if ok:
                st.session_state["ctsig_step"] = 2
                st.success("Datos guardados. Continúa en la etapa 2.")
                st.rerun()
            else:
                st.error(f"No se pudo guardar el cliente (HTTP {code}): {_detail(data)}")
    with c2:
        if st.button("Cancelar y volver al panel", use_container_width=True, key="ctsig_s1_cancel"):
            st.query_params.clear()
            st.rerun()


def _render_step2_sign(
    appointment_id: int,
    customer_id: int,
    customer: dict[str, Any],
    appointment: dict[str, Any],
) -> None:
    st.markdown("#### Etapa 2 — Firma del contrato")
    birth_d = _parse_date(customer.get("birth_date"))
    is_minor = _is_minor_by_birth_date(birth_d)
    if is_minor != bool(customer.get("is_minor")):
        is_minor = bool(customer.get("is_minor"))

    if is_minor:
        st.markdown("##### Datos del tutor o representante (obligatorios para menores)")
        st.caption(
            "Completa todos los campos. Se guardarán en el expediente al firmar. "
            "La **firma del tutor**, **fotos del documento** y la **declaración al pie del contrato** son obligatorias."
        )
        g1, g2 = st.columns(2)
        with g1:
            st.text_input(
                "Nombre completo del tutor o representante *",
                value=str(customer.get("guardian_name") or ""),
                key="ctsig_s2_gn",
                help="Nombre del padre, madre o tutor legal.",
            )
            st.selectbox(
                "Tipo de documento del tutor *",
                ["CC", "TI", "CE", "PAS"],
                index=_doc_type_index(customer.get("guardian_document_type")),
                format_func=lambda x: {"CC": "CC — Cédula", "TI": "TI — Tarjeta identidad", "CE": "CE — Extranjería", "PAS": "PAS — Pasaporte"}[x],
                key="ctsig_s2_gdt",
            )
            st.text_input(
                "Número de documento del tutor *",
                value=str(customer.get("guardian_document_number") or ""),
                key="ctsig_s2_gdn",
            )
        with g2:
            min_date_100, max_date_today = _date_range_100y()
            gdi_raw = customer.get("guardian_document_issue_date")
            st.date_input(
                "Fecha de expedición del documento del tutor *",
                value=_clamp_date(_parse_date(gdi_raw), min_date_100, max_date_today) if gdi_raw else date(2000, 1, 1),
                min_value=min_date_100,
                max_value=max_date_today,
                key="ctsig_s2_gdi",
                format="DD/MM/YYYY",
            )
        st.divider()

    kind = appointment_to_contract_kind(appointment)

    ok_t, code_t, templates = api_client.get_templates(True, contract_kind=kind)
    if not ok_t or not isinstance(templates, list):
        st.error(f"No se pudo cargar plantillas (HTTP {code_t}).")
        return
    if not templates:
        st.error(
            f"No hay plantilla de contrato **activa** para **{KIND_LABEL_ES[kind]}**. "
            "Crea y activa una en **Gestión de contratos**."
        )
        return
    if len(templates) > 1:
        st.warning(
            "Hay más de una plantilla activa para este tipo de trabajo; se usa la primera. "
            "Deje solo una activa en administración."
        )

    tpl = templates[0]
    selected_tid = int(tpl.get("id") or 0)
    ok_tpl, code_tpl, tpl_full = api_client.get_template(selected_tid)
    if not ok_tpl or not isinstance(tpl_full, dict):
        st.error(f"No se pudo abrir la plantilla (HTTP {code_tpl}): {_detail(tpl_full)}")
        return

    base_contract = _render_contract_text(str(tpl_full.get("content", "")), customer)
    fecha_firma_es = date.today().strftime("%d/%m/%Y")
    tutor_name_preview = ""
    if is_minor:
        tutor_name_preview = (st.session_state.get("ctsig_s2_gn") or customer.get("guardian_name") or "").strip()
    tpl_escaped = html_mod.escape(str(tpl_full.get("name", "") or ""))
    ver_escaped = html_mod.escape(str(tpl_full.get("version", "") or ""))
    fn_cli = html_mod.escape(
        f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip()
    )
    dt_cli = html_mod.escape(str(customer.get("document_type") or ""))
    dn_cli = html_mod.escape(str(customer.get("document_number") or "").strip())
    st.markdown(
        f"""
        <style>
        .soft-contract-body {{
            background: #faf8f5;
            color: #2d2d2d;
            border: 1px solid #d7d2c7;
            border-radius: 10px;
            padding: 14px 16px;
            margin-bottom: 8px;
            max-height: 420px;
            overflow-y: auto;
            font-size: 0.95rem;
            line-height: 1.55;
        }}
        .soft-contract-body p {{ margin: 0.45em 0; }}
        .ctsig-contract-meta {{
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            gap: 0.75rem;
            font-size: 0.88rem;
            color: #2d2d2d;
            padding: 0.4rem 0 0.55rem 0;
            margin-bottom: 0.35rem;
            border-bottom: 1px solid rgba(215, 210, 199, 0.75);
        }}
        .ctsig-declaration-alert {{
            background: #faf8f5;
            color: #2d2d2d;
            border: 1px solid #d7d2c7;
            border-radius: 10px;
            padding: 14px 16px;
            margin-bottom: 10px;
            font-size: 0.95rem;
            line-height: 1.55;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="ctsig-contract-meta">'
        f"<span><strong>{tpl_escaped}</strong> · v{ver_escaped} · {html_mod.escape(fecha_firma_es)}</span>"
        f"<span><strong>Cliente:</strong> {fn_cli} · {dt_cli} {dn_cli}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="soft-contract-body">{base_contract}</div>',
        unsafe_allow_html=True,
    )
    if is_minor:
        st.markdown(
            _minor_guardian_declaration_panel_html(
                customer, appointment, tutor_name=tutor_name_preview
            ),
            unsafe_allow_html=True,
        )
    st.warning(CONTRACT_NO_REFUND_NOTICE)
    if is_minor:
        st.info("Menor de edad: firma del cliente, del tutor, fotos del documento del tutor y firma del profesional.")

    st.markdown("##### Firmas")
    st.caption("Completa cada recuadro en la cuadrícula; el diseño se adapta al ancho disponible.")
    _sig_w, _sig_h = 340, 170
    sig_cols = st.columns(3) if is_minor else st.columns(2)
    with sig_cols[0]:
        client_signature = _signature_pad_b64(
            "Firma del cliente", "ctsig_client", canvas_width=_sig_w, canvas_height=_sig_h
        )
    tutor_signature = None
    tutor_doc_front = None
    tutor_doc_back = None
    if is_minor:
        with sig_cols[1]:
            tutor_signature = _signature_pad_b64(
                "Firma del tutor o representante *",
                "ctsig_tutor",
                canvas_width=_sig_w,
                canvas_height=_sig_h,
            )
        with sig_cols[2]:
            artist_signature = _signature_pad_b64(
                "Firma del tatuador/perforador",
                "ctsig_artist",
                canvas_width=_sig_w,
                canvas_height=_sig_h,
            )
    else:
        with sig_cols[1]:
            artist_signature = _signature_pad_b64(
                "Firma del tatuador/perforador",
                "ctsig_artist",
                canvas_width=_sig_w,
                canvas_height=_sig_h,
            )

    if is_minor:
        st.markdown("##### Documento del tutor (fotos)")
        st.caption("Pulsa **Activar cámara** en cada lado; luego captura la foto del documento.")
        fk = f"ctsig_cam_front_on_{appointment_id}"
        bk = f"ctsig_cam_back_on_{appointment_id}"
        if fk not in st.session_state:
            st.session_state[fk] = False
        if bk not in st.session_state:
            st.session_state[bk] = False
        cam1, cam2 = st.columns(2)
        with cam1:
            if st.button("Activar cámara — anverso", key=f"ctsig_btn_camf_{appointment_id}", use_container_width=True):
                st.session_state[fk] = True
            if st.session_state[fk]:
                tutor_doc_front = _image_file_to_base64(
                    st.camera_input(
                        "Captura el anverso del documento del tutor",
                        key=f"ctsig_tutor_front_{appointment_id}",
                    )
                )
        with cam2:
            if st.button("Activar cámara — reverso", key=f"ctsig_btn_camb_{appointment_id}", use_container_width=True):
                st.session_state[bk] = True
            if st.session_state[bk]:
                tutor_doc_back = _image_file_to_base64(
                    st.camera_input(
                        "Captura el reverso del documento del tutor",
                        key=f"ctsig_tutor_back_{appointment_id}",
                    )
                )
    else:
        tutor_doc_front = None
        tutor_doc_back = None

    nav1, nav2, nav3 = st.columns(3)
    with nav1:
        if st.button("← Volver a datos personales", use_container_width=True, key="ctsig_s2_back"):
            st.session_state["ctsig_step"] = 1
            st.rerun()

    with nav3:
        if st.button("Guardar contrato firmado", type="primary", use_container_width=True, key="ctsig_save"):
            if not client_signature:
                st.error("La firma del cliente es obligatoria.")
                return
            if not artist_signature:
                st.error("La firma del tatuador/perforador es obligatoria.")
                return

            cust_snapshot = dict(customer)
            if is_minor:
                gn = (st.session_state.get("ctsig_s2_gn") or "").strip()
                gdt = str(st.session_state.get("ctsig_s2_gdt") or "CC")
                gdn = (st.session_state.get("ctsig_s2_gdn") or "").strip()
                gdi_d = st.session_state.get("ctsig_s2_gdi")
                if not isinstance(gdi_d, date):
                    gdi_d = _parse_date(gdi_d)
                if len(gn) < 3:
                    st.error("El nombre del tutor o representante debe tener al menos 3 caracteres.")
                    return
                if not gdn or len(gdn) < 5:
                    st.error("El número de documento del tutor es obligatorio (mín. 5 caracteres).")
                    return
                if gdt == "TI":
                    st.error("El tipo de documento del tutor no puede ser TI.")
                    return
                today = date.today()
                tutor_years = today.year - gdi_d.year - ((today.month, today.day) < (gdi_d.month, gdi_d.day))
                if tutor_years < 18:
                    st.error("La expedición del documento del tutor debe tener al menos 18 años de antigüedad respecto a hoy.")
                    return
                if not tutor_signature:
                    st.error("La firma del tutor o representante es obligatoria para menores.")
                    return
                if not tutor_doc_front or not tutor_doc_back:
                    st.error("Debes activar la cámara y capturar el anverso y el reverso del documento del tutor.")
                    return

                put_base = _put_payload_from_customer(cust_snapshot)
                put_payload = {
                    **put_base,
                    "is_minor": True,
                    "guardian_name": gn,
                    "guardian_document_type": gdt,
                    "guardian_document_number": gdn,
                    "guardian_document_issue_date": gdi_d.isoformat(),
                }
                ok_u, code_u, data_u = api_client.put_customer(customer_id, put_payload)
                if not ok_u:
                    st.error(f"No se pudieron guardar datos del tutor (HTTP {code_u}): {_detail(data_u)}")
                    return
                ok_rf, _, cust_rf = api_client.get_customer(customer_id)
                if ok_rf and isinstance(cust_rf, dict):
                    cust_snapshot = cust_rf

            contract_body = _render_contract_text(str(tpl_full.get("content", "")), cust_snapshot)
            if is_minor:
                gn_saved = (cust_snapshot.get("guardian_name") or "").strip()
                contract_body += _minor_guardian_declaration_panel_html(
                    cust_snapshot, appointment, tutor_name=gn_saved
                )

            payload = {
                "appointment_id": int(appointment_id),
                "is_minor": is_minor,
                "health_data": {"source": "contract_signing_view", "template_id": selected_tid},
                "signature": client_signature,
                "tutor_signature": tutor_signature,
                "artist_signature": artist_signature,
                "tutor_document_front": tutor_doc_front,
                "tutor_document_back": tutor_doc_back,
                "contract_text": contract_body,
                "template_id": selected_tid,
            }
            ok_s, code_s, data_s = api_client.post_contract(payload)
            if ok_s:
                st.session_state["ctsig_step"] = 3
                st.success("Contrato firmado y guardado. Continúa con el cuestionario (etapa 3).")
                st.rerun()
            else:
                st.error(f"No se pudo guardar el contrato (HTTP {code_s}): {_detail(data_s)}")


def _render_step3_questionnaire(appointment_id: int) -> None:
    st.markdown("#### Etapa 3 — Cuestionario")
    st.success("Contrato registrado correctamente.")
    st.info(
        "**Cuestionario de salud / consentimientos ampliados — en construcción.** "
        "Próximamente podrás completar formularios adicionales vinculados a esta cita."
    )
    st.caption(f"Cita #{appointment_id}")
    if st.button("Volver al panel principal", type="primary", use_container_width=True, key="ctsig_s3_done"):
        st.query_params.clear()
        st.session_state.pop("ctsig_step", None)
        st.session_state.pop("ctsig_aid", None)
        st.rerun()


def render_contract_signing_view(appointment_id: int) -> None:
    aid = int(appointment_id)
    if st.session_state.get("ctsig_aid") != aid:
        st.session_state["ctsig_aid"] = aid
        st.session_state["ctsig_step"] = 1

    step = int(st.session_state.get("ctsig_step", 1))
    if step not in (1, 2, 3):
        step = 1
        st.session_state["ctsig_step"] = 1

    st.subheader("Firma digital de contrato")
    _steps_progress(step)

    if st.button("Volver al panel principal", key="ctsig_back"):
        st.query_params.clear()
        st.session_state.pop("ctsig_step", None)
        st.session_state.pop("ctsig_aid", None)
        st.rerun()

    ok_a, code_a, appts = api_client.get_appointments()
    if not ok_a or not isinstance(appts, list):
        st.error(f"No se pudo cargar citas (HTTP {code_a}): {_detail(appts)}")
        return

    appt = next((a for a in appts if int(a.get("id", 0)) == aid), None)
    if not appt:
        st.error("Cita no encontrada.")
        return
    if not service_type_requires_contract(appt.get("service_type")):
        st.info(
            "Las citas de tipo **Cambio** o **Limpieza** no requieren firma de contrato digital."
        )
        st.caption(f"Servicio registrado: `{appt.get('service_type', '—')}`")
        if st.button("Volver al panel principal", type="primary", key="ctsig_no_contract_back"):
            st.query_params.clear()
            st.session_state.pop("ctsig_step", None)
            st.session_state.pop("ctsig_aid", None)
            st.rerun()
        return
    customer_id_raw = appt.get("customer_id")
    if not customer_id_raw:
        st.error("La cita no tiene cliente vinculado.")
        return
    customer_id = int(customer_id_raw)

    ok_c, code_c, customer = api_client.get_customer(customer_id)
    if not ok_c or not isinstance(customer, dict):
        st.error(f"No se pudo cargar cliente (HTTP {code_c}): {_detail(customer)}")
        return

    if step == 1:
        _render_step1_personal(customer_id, customer)
        return
    if step == 2:
        ok_c2, code_c2, customer2 = api_client.get_customer(customer_id)
        if not ok_c2 or not isinstance(customer2, dict):
            st.error(f"No se pudo recargar cliente (HTTP {code_c2}).")
            return
        _render_step2_sign(aid, customer_id, customer2, appt)
        return
    _render_step3_questionnaire(aid)
