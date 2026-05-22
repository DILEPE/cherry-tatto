"""Flujo de firma de contrato en el panel (3 etapas: datos, cuestionario, firma).

Se abre vía query params del mismo Streamlit (`?view=contract_sign&appointment_id=...`) con sesión del panel;
usar `panel_navigation.open_contract_signing` en lugar de enlaces externos para no perder la sesión.

Solo firma del profesional (cliente ya firmó): `contract_artist_only=1` — ver `open_contract_artist_signature`.
"""
from __future__ import annotations

import base64
import html as html_mod
import io
import sys
from datetime import date
from typing import Any, Optional

import json

import streamlit as st
from pydantic import ValidationError

from app.schemas.customer import CUSTOMER_BIRTH_PENDING, CustomerCreate, SOCIAL_MEDIA_MAX_LEN
from app.domain.contract_kinds import KIND_LABEL_ES, appointment_to_contract_kind, service_type_requires_contract
from app.domain.contract_signing_guard import appointment_must_be_fully_paid_for_contract
from app.domain.survey_question_helpers import QUESTION_TYPES_NEEDING_OPTIONS
from streamlit_app import api_client
from streamlit_app.panel_navigation import leave_contract_view_to_panel
from streamlit_app.customer_sync import social_media_api_to_form_text, social_media_form_text_to_api
from streamlit_app.validation import (
    mobile_phone_co_10_error,
    social_media_text_error,
    validate_appointment,
)
from streamlit_app.customers_management import (
    _clamp_date,
    _date_range_100y,
    _doc_type_index,
    _is_minor_by_birth_date,
    _parse_date,
    _validate_document_rules,
)

def _request_citas_list_refresh() -> None:
    """Tras guardar contrato en API: obligar a GET /appointments en la próxima vista de citas (botones al día)."""
    st.session_state["_ap_refresh_after_contract"] = True


def _panel_session_is_technician() -> bool:
    """Tatuador/perforador: mismo criterio que citas_tab (sin import circular)."""
    role = str(st.session_state.get("_panel_user_role") or "")
    return role in ("tatuador", "perforador")


CONTRACT_NO_REFUND_NOTICE = (
    "Por favor, tenga en cuenta que no hay devolución de dinero por citas apartadas, tampoco por abonos. "
    "En caso de modificaciones de último momento en los diseños, su valor puede aumentar."
)


def _toast_ok(message: str, *, icon: str = "✅") -> None:
    try:
        st.toast(message, icon=icon)
    except Exception:
        pass


_CTSIG_Q_UNSET = ""


def _contract_artist_only_query() -> bool:
    """Query param del panel: solo lienzo del profesional (cliente ya firmó)."""
    return (st.query_params.get("contract_artist_only") or "").strip().lower() in ("1", "true", "yes", "on")


def _fmt_survey_no_selection(x: str) -> str:
    return "— Selecciona —" if x == _CTSIG_Q_UNSET else str(x)


def _appointment_artist_display_name(appointment: dict[str, Any]) -> str:
    fn = str(appointment.get("assigned_first_name") or "").strip()
    ln = str(appointment.get("assigned_last_name") or "").strip()
    name = f"{fn} {ln}".strip()
    if name:
        return name
    un = str(appointment.get("assigned_username") or "").strip()
    return f"@{un}" if un else "Sin asignar"


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


def _appointment_payment_ready_for_signature(appt: dict[str, Any]) -> tuple[bool, str | None]:
    """Total del trabajo definido (> 0) y abonado al completo; misma regla para cualquier perfil del panel."""
    return appointment_must_be_fully_paid_for_contract(
        total_amount=appt.get("total_amount"),
        deposit=appt.get("deposit"),
        pending_balance=appt.get("pending_balance"),
    )


def _advance_to_contract_signature_step_after_payment_check(appointment_id: int) -> None:
    """GET fresco de la cita y avance a etapa 3 solo si el pago permite firmar."""
    ok_a, code_a, fresh = api_client.get_appointment(int(appointment_id))
    if not ok_a or not isinstance(fresh, dict):
        st.error(f"No se pudo verificar la cita (HTTP {code_a}): {_detail(fresh)}")
        return
    ok_pay, pay_err = _appointment_payment_ready_for_signature(fresh)
    if not ok_pay:
        st.error(pay_err or "Completa el abono antes de firmar el contrato.")
        st.info(
            "Abre **Gestión de citas**, localiza esta cita y usa **Montos** hasta dejar **saldo pendiente** en cero "
            "y un **valor total** definido."
        )
        return
    st.session_state["ctsig_step"] = 3
    st.rerun()


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
    st.markdown(
        f'<span class="ctsig-signature-marker" data-w="{int(canvas_width)}" aria-hidden="true"></span>',
        unsafe_allow_html=True,
    )
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


def _signature_payload_acceptable(value: Optional[str]) -> bool:
    """True si hay firma dibujada (data URL PNG/JPEG) o texto suficiente del fallback del lienzo."""
    if value is None:
        return False
    v = str(value).strip()
    if len(v) < 80:
        return False
    if v.startswith("data:image/"):
        parts = v.split(",", 1)
        return len(parts) == 2 and len(parts[1].strip()) >= 40
    return len(v) >= 4


def _tutor_document_acceptable(value: Optional[str]) -> bool:
    if value is None:
        return False
    v = str(value).strip()
    return len(v) >= 80 and v.startswith("data:image/")


def _steps_progress(step: int) -> None:
    titles = ("Datos personales", "Cuestionario", "Firma del contrato")
    st.caption(f"Paso **{step}/3** — {titles[step - 1]}")


_CTSIG_CACHE_KEYS = ("ctsig_tpl_bundle", "ctsig_survey_q_kind", "ctsig_survey_q_list")


def _ctsig_clear_contract_caches() -> None:
    for k in _CTSIG_CACHE_KEYS:
        st.session_state.pop(k, None)


def _exit_contract_signing_to_panel() -> None:
    """Vuelve al panel preservando la sesión (solo se limpian params y estado del asistente de firma)."""
    st.session_state.pop("_ctsig_pending_toast", None)
    st.session_state.pop("ctsig_step", None)
    st.session_state.pop("ctsig_aid", None)
    _ctsig_clear_contract_caches()
    for k in list(st.session_state.keys()):
        if isinstance(k, str) and k.startswith("ctsig_expr_"):
            st.session_state.pop(k, None)
    st.session_state.pop("ctsig_skip_init_step", None)
    st.session_state.pop("ctsig_artist_only", None)
    leave_contract_view_to_panel()


def _load_contract_template_bundle(kind: str) -> tuple[bool, str | None, dict[str, Any] | None, int]:
    """Plantilla activa y contenido HTML; cache en sesión para no repetir GET en cada rerun."""
    bundle = st.session_state.get("ctsig_tpl_bundle")
    if isinstance(bundle, dict) and bundle.get("kind") == kind:
        tf = bundle.get("tpl_full")
        tid = bundle.get("selected_tid")
        if isinstance(tf, dict) and isinstance(tid, int) and tid > 0:
            return True, None, tf, tid
    ok_t, code_t, templates = api_client.get_templates(True, contract_kind=kind)
    if not ok_t or not isinstance(templates, list):
        return False, f"No se pudo cargar plantillas (HTTP {code_t}).", None, 0
    if not templates:
        return (
            False,
            (
                f"No hay plantilla de contrato **activa** para **{KIND_LABEL_ES[kind]}**. "
                "Crea y activa una en **Gestión de contratos**."
            ),
            None,
            0,
        )
    if len(templates) > 1:
        st.warning(
            "Hay más de una plantilla activa para este tipo de trabajo; se usa la primera. "
            "Deje solo una activa en administración."
        )
    tpl0 = templates[0]
    selected_tid = int(tpl0.get("id") or 0)
    ok_tpl, code_tpl, tpl_full = api_client.get_template(selected_tid)
    if not ok_tpl or not isinstance(tpl_full, dict):
        return False, f"No se pudo abrir la plantilla (HTTP {code_tpl}): {_detail(tpl_full)}", None, 0
    st.session_state["ctsig_tpl_bundle"] = {"kind": kind, "tpl_full": tpl_full, "selected_tid": selected_tid}
    return True, None, tpl_full, selected_tid


def _survey_questions_cached(contract_kind: str) -> tuple[bool, int, Any]:
    ck = st.session_state.get("ctsig_survey_q_kind")
    qs = st.session_state.get("ctsig_survey_q_list")
    if ck == contract_kind and isinstance(qs, list):
        return True, 200, qs
    ok_q, code_q, questions = api_client.get_survey_questions(
        include_inactive=False,
        contract_kind=contract_kind,
    )
    if ok_q and isinstance(questions, list):
        st.session_state["ctsig_survey_q_kind"] = contract_kind
        st.session_state["ctsig_survey_q_list"] = questions
    return ok_q, code_q, questions


def _render_step1_personal(customer_id: int, customer: dict[str, Any], appointment: dict[str, Any]) -> None:
    st.markdown("#### Etapa 1 — Completar datos del cliente")
    st.caption(
        "Para **firmar el contrato**, todos los campos marcados con * son obligatorios en esta pantalla "
        "(solo validación en el panel; la API de clientes no cambia). "
        "Si la fecha de nacimiento indica **menor de edad**, completarás datos del tutor en la **etapa 3 (firma)**."
    )
    min_date_100, max_date_today = _date_range_100y()
    ed = customer
    if _parse_date(ed.get("birth_date")) == CUSTOMER_BIRTH_PENDING:
        st.info(
            "Cliente registrado solo con agendamiento: **aún no hay fecha de nacimiento real**. "
            "Indica la fecha correcta aquí para detectar menor de edad y el tutor en la etapa de firma."
        )

    a, b = st.columns(2)
    with a:
        st.text_input("Nombre *", value=str(ed.get("first_name") or ""), key="ctsig_s1_fn")
        st.text_input("Apellido *", value=str(ed.get("last_name") or ""), key="ctsig_s1_ln")
        bd_raw = st.date_input(
            "Fecha de nacimiento *",
            value=_clamp_date(_parse_date(ed.get("birth_date")), min_date_100, max_date_today),
            min_value=min_date_100,
            max_value=max_date_today,
            key="ctsig_s1_bd",
            format="DD/MM/YYYY",
        )
        bd = bd_raw if isinstance(bd_raw, date) else _parse_date(bd_raw)
        if bd != CUSTOMER_BIRTH_PENDING and _is_minor_by_birth_date(bd):
            st.warning(
                "**Menor de edad:** en la **etapa 3 (Firma)** deberás completar los datos del tutor o representante "
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
            "Registrar fecha de expedición del documento del cliente *",
            value=bool(eddi_raw),
            key="ctsig_s1_has_ddi",
            help="Para firmar el contrato desde el panel es obligatorio indicar la expedición del documento.",
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
            "Nacionalidad *",
            value=str(ed.get("nationality") or ""),
            key="ctsig_s1_nat",
        )
        st.text_input(
            "Profesión *",
            value=str(ed.get("profession") or ""),
            key="ctsig_s1_prof",
        )

    with st.expander("Contacto y redes (obligatorio para firma)", expanded=True):
        st.text_input("Dirección *", value=str(ed.get("address") or ""), key="ctsig_s1_addr")
        st.text_area(
            "Redes sociales *",
            value=social_media_api_to_form_text(ed.get("social_media")),
            height=70,
            key="ctsig_s1_sm",
            max_chars=SOCIAL_MEDIA_MAX_LEN,
            help=f"Texto plano, máximo {SOCIAL_MEDIA_MAX_LEN} caracteres (@, enlaces, etc.). No es JSON.",
        )

    with st.expander("Contacto de emergencia (obligatorio para firma)", expanded=True):
        st.text_input("Nombre contacto emergencia *", value=str(ed.get("emergency_contact_name") or ""), key="ctsig_s1_ecn")
        st.text_input(
            "Celular contacto emergencia *",
            value=str(ed.get("emergency_contact_phone") or ""),
            key="ctsig_s1_ecp",
            help="10 dígitos (obligatorio para firmar desde esta vista).",
        )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Guardar y continuar al cuestionario", type="primary", use_container_width=True, key="ctsig_s1_next"):
            fn = (st.session_state.get("ctsig_s1_fn") or "").strip()
            ln = (st.session_state.get("ctsig_s1_ln") or "").strip()
            if len(fn) < 1 or len(ln) < 1:
                st.error("Nombre y apellido son obligatorios.")
                return
            bd_v = st.session_state.get("ctsig_s1_bd")
            if not isinstance(bd_v, date):
                bd_v = _parse_date(bd_v) if bd_v not in (None, "") else None
            if bd_v is None:
                st.error("La **fecha de nacimiento** es obligatoria.")
                return
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
            if not has_ddi:
                st.error(
                    "Para firmar el contrato debes marcar **Registrar fecha de expedición del documento** "
                    "e indicar la fecha correcta."
                )
                return
            ddi_v = st.session_state.get("ctsig_s1_ddi")
            if not isinstance(ddi_v, date):
                ddi_v = _parse_date(ddi_v)
            doc_err = _validate_document_rules(
                birth_date=bd_v,
                document_type=dt,
                has_document_issue_date=True,
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
            nat = (st.session_state.get("ctsig_s1_nat") or "").strip()
            if len(nat) < 2:
                st.error("La **nacionalidad** es obligatoria para firmar el contrato.")
                return
            prof = (st.session_state.get("ctsig_s1_prof") or "").strip()
            if len(prof) < 2:
                st.error("La **profesión** es obligatoria para firmar el contrato.")
                return
            addr = (st.session_state.get("ctsig_s1_addr") or "").strip()
            if len(addr) < 5:
                st.error("La **dirección** es obligatoria para firmar el contrato (al menos 5 caracteres).")
                return
            sm_raw = st.session_state.get("ctsig_s1_sm") or ""
            sm_err = social_media_text_error(str(sm_raw))
            if sm_err:
                st.error(sm_err)
                return
            sm_for_api = social_media_form_text_to_api(str(sm_raw))
            if not sm_for_api:
                st.error("Indica **redes sociales** (texto breve: usuario @, red o enlace).")
                return
            ecn = (st.session_state.get("ctsig_s1_ecn") or "").strip()
            if len(ecn) < 3:
                st.error("El **nombre del contacto de emergencia** es obligatorio.")
                return
            ecp = (st.session_state.get("ctsig_s1_ecp") or "").strip()
            ecp_err = mobile_phone_co_10_error(ecp)
            if ecp_err:
                st.error(f"Celular de emergencia: {ecp_err}")
                return

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
                ok_pay, pay_err = _appointment_payment_ready_for_signature(appointment)
                if not ok_pay:
                    st.error(pay_err or "Completa el abono antes de firmar el contrato.")
                    return
                st.session_state["ctsig_step"] = 2
                st.session_state["_ctsig_pending_toast"] = "Datos del cliente actualizados correctamente."
                st.success("Datos guardados. Continúa en la etapa 2 (cuestionario).")
                st.rerun()
            else:
                st.error(f"No se pudo guardar el cliente (HTTP {code}): {_detail(data)}")
    with c2:
        if st.button("Cancelar y volver al panel", use_container_width=True, key="ctsig_s1_cancel"):
            _exit_contract_signing_to_panel()


def _render_step3_sign_contract(
    appointment_id: int,
    customer_id: int,
    customer: dict[str, Any],
    appointment: dict[str, Any],
) -> None:
    st.markdown("#### Etapa 3 — Firma del contrato")
    ok_pay, pay_err = _appointment_payment_ready_for_signature(appointment)
    if not ok_pay:
        st.error(pay_err or "Completa el abono antes de firmar el contrato.")
        st.info(
            "Abre **Gestión de citas**, localiza esta cita y usa **Montos** hasta dejar **saldo pendiente** en cero."
        )
        if st.button("← Volver a datos personales", use_container_width=True, key="ctsig_s2_pay_block_back"):
            st.session_state["ctsig_step"] = 1
            st.rerun()
        return
    birth_d = _parse_date(customer.get("birth_date"))
    is_minor = _is_minor_by_birth_date(birth_d)
    if is_minor != bool(customer.get("is_minor")):
        is_minor = bool(customer.get("is_minor"))

    kind = appointment_to_contract_kind(appointment)
    tpl_ok, tpl_err, tpl_full, selected_tid = _load_contract_template_bundle(kind)
    if not tpl_ok or tpl_full is None or selected_tid <= 0:
        st.error(tpl_err or "Plantilla no disponible.")
        return

    base_contract = _render_contract_text(str(tpl_full.get("content", "")), customer)
    fecha_firma_es = date.today().strftime("%d/%m/%Y")
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
    st.warning(CONTRACT_NO_REFUND_NOTICE)
    if is_minor:
        st.info(
            "Menor de edad: firma del cliente, del tutor, fotos del documento del tutor y firma del profesional "
            "(esta última puede completarla el tatuador/perforador después desde la agenda)."
        )

    @st.fragment
    def _fragment_firmas_y_guardado() -> None:
        tutor_name_preview = ""
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
            tutor_name_preview = (st.session_state.get("ctsig_s2_gn") or customer.get("guardian_name") or "").strip()
            st.markdown(
                _minor_guardian_declaration_panel_html(
                    customer, appointment, tutor_name=tutor_name_preview
                ),
                unsafe_allow_html=True,
            )

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
                    "Firma del tatuador/perforador (opcional aquí)",
                    "ctsig_artist",
                    canvas_width=_sig_w,
                    canvas_height=_sig_h,
                )
        else:
            with sig_cols[1]:
                artist_signature = _signature_pad_b64(
                    "Firma del tatuador/perforador (opcional aquí)",
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

        nav1, _nav2, nav3 = st.columns(3)
        with nav1:
            if st.button("← Volver al cuestionario", use_container_width=True, key="ctsig_s2_back"):
                st.session_state["ctsig_step"] = 2
                st.rerun()

        with nav3:
            if st.button("Guardar contrato firmado", type="primary", use_container_width=True, key="ctsig_save"):
                ok_rf, code_rf, appt_chk = api_client.get_appointment(int(appointment_id))
                appt_for_pay = appt_chk if ok_rf and isinstance(appt_chk, dict) else appointment
                ok_pay2, pay_err2 = _appointment_payment_ready_for_signature(appt_for_pay)
                if not ok_pay2:
                    st.error(pay_err2 or "Saldo pendiente: no se puede firmar.")
                    return

                firmas_pendientes: list[str] = []
                if not _signature_payload_acceptable(client_signature):
                    firmas_pendientes.append("**Firma del cliente** — dibuja en el primer recuadro.")
                if is_minor:
                    if not _signature_payload_acceptable(tutor_signature):
                        firmas_pendientes.append("**Firma del tutor** — obligatoria para menores.")
                    if not _tutor_document_acceptable(tutor_doc_front):
                        firmas_pendientes.append("**Foto anverso** del documento del tutor.")
                    if not _tutor_document_acceptable(tutor_doc_back):
                        firmas_pendientes.append("**Foto reverso** del documento del tutor.")
                if firmas_pendientes:
                    st.warning("No se puede guardar el contrato sin las firmas y documentación obligatorias.")
                    st.error(
                        "Completa lo siguiente y vuelve a pulsar **Guardar**:\n\n"
                        + "\n".join(f"- {x}" for x in firmas_pendientes)
                    )
                    try:
                        st.toast("Faltan firmas o fotos obligatorias.", icon="⚠️")
                    except Exception:
                        pass
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
                        st.error(
                            "La expedición del documento del tutor debe tener al menos 18 años de antigüedad respecto a hoy."
                        )
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
                    _request_citas_list_refresh()
                    st.session_state["_panel_pending_toast"] = "Contrato firmado y registrado correctamente."
                    _panel_principal_from_step3()
                else:
                    st.error(f"No se pudo guardar el contrato (HTTP {code_s}): {_detail(data_s)}")

    _fragment_firmas_y_guardado()


def _panel_principal_from_step3() -> None:
    _exit_contract_signing_to_panel()


def _survey_number_is_money(q: dict[str, Any]) -> bool:
    lbl = str(q.get("label") or "").lower()
    return "valor" in lbl and "procedimiento" in lbl


def _survey_number_input_kwargs(q: dict[str, Any]) -> dict[str, Any]:
    """COP entero para valor del procedimiento; floats evitan warning de Streamlit int/%.0f."""
    if _survey_number_is_money(q):
        return {"min_value": 0.0, "value": None, "step": 1000.0}
    return {"min_value": 0.0, "value": None, "step": 1.0}


def _parse_survey_number_value(q: dict[str, Any], raw: Any) -> float:
    if raw is None or raw == "":
        raise ValueError("vacío")
    if _survey_number_is_money(q):
        return float(int(round(float(raw))))
    return float(raw)


def _submit_ctsig_survey(appointment_id: int, qs: list[dict[str, Any]]) -> None:
    errors: list[str] = []
    wr_raw = str(st.session_state.get("ctsig_s3_would_rec") or "").strip()
    if wr_raw == "" or wr_raw == _CTSIG_Q_UNSET:
        errors.append("Indica si **recomendaría nuestros servicios**.")
    would_rec = wr_raw == "Sí"
    items: list[dict[str, Any]] = []
    for q in qs:
        qid = int(q["id"])
        qt = str(q.get("question_type") or "text_short")
        lbl = str(q.get("label") or "Pregunta")
        raw_o = q.get("options")
        opts = [str(x).strip() for x in raw_o] if isinstance(raw_o, list) else []
        opts = [x for x in opts if x]
        sk = f"ctsig3_{qid}"
        if qt == "rating_1_5":
            raw_r = str(st.session_state.get(f"{sk}_r") or "").strip()
            if raw_r == "" or raw_r == _CTSIG_Q_UNSET:
                errors.append(f"Selecciona una calificación (1–5) en «{lbl}».")
            else:
                items.append({"question_id": qid, "rating": int(raw_r)})
        elif qt == "yes_no":
            yn = str(st.session_state.get(f"{sk}_yn") or "").strip()
            if yn == "" or yn == _CTSIG_Q_UNSET:
                errors.append(f"Responde **sí o no** en «{lbl}».")
            else:
                items.append({"question_id": qid, "yes_no": yn == "Sí"})
        elif qt in ("text", "textarea", "text_short"):
            t = str(st.session_state.get(f"{sk}_t") or "").strip()
            if not t:
                errors.append(f"Completa «{lbl}».")
            else:
                items.append({"question_id": qid, "text": t})
        elif qt == "number":
            n_raw = st.session_state.get(f"{sk}_n")
            try:
                num_val = _parse_survey_number_value(q, n_raw)
                if _survey_number_is_money(q) and num_val <= 0:
                    errors.append(f"Indica el valor en «{lbl}».")
                else:
                    items.append({"question_id": qid, "number": num_val})
            except (TypeError, ValueError):
                errors.append(f"Indica un número válido en «{lbl}».")
        elif qt in QUESTION_TYPES_NEEDING_OPTIONS:
            if len(opts) < 2:
                errors.append(f"La pregunta «{lbl}» no está bien configurada (faltan opciones).")
                continue
            if qt == "radio":
                choice = st.session_state.get(f"{sk}_radio")
                if choice is None or str(choice).strip() == "" or choice == _CTSIG_Q_UNSET:
                    errors.append(f"Elige una opción en «{lbl}».")
                else:
                    items.append({"question_id": qid, "text": str(choice).strip()})
            elif qt == "select":
                choice = st.session_state.get(f"{sk}_sel")
                if choice is None or str(choice).strip() == "" or choice == _CTSIG_Q_UNSET:
                    errors.append(f"Elige una opción en «{lbl}».")
                else:
                    items.append({"question_id": qid, "text": str(choice).strip()})
            else:
                choice_list = st.session_state.get(f"{sk}_cb")
                if choice_list is None:
                    choice_list = []
                if not isinstance(choice_list, list):
                    choice_list = []
                cleaned = [str(x).strip() for x in choice_list if str(x).strip()]
                if not cleaned:
                    errors.append(f"Marca **al menos una opción** en «{lbl}».")
                else:
                    items.append({"question_id": qid, "choices": cleaned})
        else:
            t = str(st.session_state.get(f"{sk}_t") or "").strip()
            if not t:
                errors.append(f"Completa «{lbl}».")
            else:
                items.append({"question_id": qid, "text": t})

    if errors:
        for e in errors:
            st.error(e)
        return

    payload: dict[str, Any] = {
        "appointment_id": int(appointment_id),
        "would_recommend": bool(would_rec),
        "answers": items,
    }
    ok_p, code_p, data_p = api_client.post_survey(payload)
    if ok_p:
        ok_a, code_a, fresh_appt = api_client.get_appointment(int(appointment_id))
        if not ok_a or not isinstance(fresh_appt, dict):
            st.error(f"No se pudo verificar pagos de la cita (HTTP {code_a}): {_detail(fresh_appt)}")
        else:
            ok_pay_go, pay_err_go = _appointment_payment_ready_for_signature(fresh_appt)
            if not ok_pay_go:
                st.error(pay_err_go or "Completa el abono antes de firmar el contrato.")
                st.info(
                    "El cuestionario quedó guardado. Registra **Montos** en la cita y vuelve aquí para continuar a la firma."
                )
            else:
                st.session_state["_ctsig_pending_toast"] = "Encuesta completada y guardada correctamente."
                st.success("Cuestionario enviado. Continúa con la firma del contrato (etapa 3).")
                st.session_state["ctsig_step"] = 3
                st.rerun()
    else:
        st.error(f"No se pudo guardar el cuestionario (HTTP {code_p}): {_detail(data_p)}")


def _render_contract_survey_question(q: dict[str, Any]) -> None:
    """Etiqueta (altura mínima para alinear columnas) + widget; sin divisor."""
    lbl = str(q.get("label") or "Pregunta")
    st.markdown(
        f'<div class="ctsig-survey-q-label">{html_mod.escape(lbl)}</div>',
        unsafe_allow_html=True,
    )
    qid = int(q["id"])
    qt = str(q.get("question_type") or "text_short")
    raw_o = q.get("options")
    opts = [str(x).strip() for x in raw_o] if isinstance(raw_o, list) else []
    opts = [x for x in opts if x]
    sk = f"ctsig3_{qid}"
    if qt == "rating_1_5":
        st.selectbox(
            "Valor",
            options=["", "1", "2", "3", "4", "5"],
            format_func=_fmt_survey_no_selection,
            key=f"{sk}_r",
            label_visibility="collapsed",
        )
    elif qt == "yes_no":
        st.selectbox(
            "Respuesta",
            options=["", "Sí", "No"],
            format_func=_fmt_survey_no_selection,
            key=f"{sk}_yn",
            label_visibility="collapsed",
        )
    elif qt == "textarea":
        st.text_area(
            "Tu respuesta", max_chars=5000, height=160, key=f"{sk}_t", label_visibility="collapsed"
        )
    elif qt == "text_short":
        st.text_input("Tu respuesta", max_chars=500, key=f"{sk}_t", label_visibility="collapsed")
    elif qt == "text":
        st.text_area(
            "Tu respuesta", max_chars=5000, height=120, key=f"{sk}_t", label_visibility="collapsed"
        )
    elif qt == "number":
        num_kw = _survey_number_input_kwargs(q)
        st.number_input(
            "Valor numérico",
            key=f"{sk}_n",
            label_visibility="collapsed",
            placeholder="0" if _survey_number_is_money(q) else None,
            **num_kw,
        )
    elif qt == "radio":
        if len(opts) < 2:
            st.error("Esta pregunta no tiene opciones configuradas; avisa al administrador.")
        else:
            st.selectbox(
                "Elige una opción",
                options=[_CTSIG_Q_UNSET, *opts],
                format_func=_fmt_survey_no_selection,
                key=f"{sk}_radio",
                label_visibility="collapsed",
            )
    elif qt == "select":
        if len(opts) < 2:
            st.error("Esta pregunta no tiene opciones configuradas; avisa al administrador.")
        else:
            st.selectbox(
                "Elige una opción",
                options=[_CTSIG_Q_UNSET, *opts],
                format_func=_fmt_survey_no_selection,
                key=f"{sk}_sel",
                label_visibility="collapsed",
            )
    elif qt == "checkbox":
        if len(opts) < 2:
            st.error("Esta pregunta no tiene opciones configuradas; avisa al administrador.")
        else:
            st.multiselect(
                "Marca una o varias opciones",
                options=opts,
                key=f"{sk}_cb",
                label_visibility="collapsed",
            )
    else:
        st.text_input("Tu respuesta", max_chars=500, key=f"{sk}_t", label_visibility="collapsed")


def _render_step2_questionnaire(appointment_id: int, appt: dict[str, Any]) -> None:
    st.markdown("#### Etapa 2 — Cuestionario")
    st.caption(
        "Completa el formulario antes de la firma. "
        f"Cita #{appointment_id}"
    )

    ok_s, code_s, lookup = api_client.get_survey_for_appointment(appointment_id)
    if ok_s and isinstance(lookup, dict) and lookup.get("found"):
        st.info("El cuestionario para esta cita **ya fue enviado**. Puedes continuar a la firma del contrato.")
        b1, b2 = st.columns(2)
        with b1:
            if st.button(
                "Continuar a firma del contrato",
                type="primary",
                use_container_width=True,
                key="ctsig_s3_skip_to_sign",
            ):
                _advance_to_contract_signature_step_after_payment_check(appointment_id)
        with b2:
            if st.button("Volver al panel principal", use_container_width=True, key="ctsig_s3_done_existing"):
                _panel_principal_from_step3()
        return

    kind = appointment_to_contract_kind(appt)
    ok_q, code_q, questions = _survey_questions_cached(kind)
    if not ok_q or not isinstance(questions, list):
        st.error(f"No se pudieron cargar las preguntas (HTTP {code_q}): {_detail(questions)}")
        if st.button("Volver al panel principal", use_container_width=True, key="ctsig_s3_errq"):
            _panel_principal_from_step3()
        return

    qs = sorted(
        questions,
        key=lambda x: (int(x.get("sort_order") or 0), int(x.get("id") or 0)),
    )
    if not qs:
        st.info(
            "No hay preguntas activas en el sistema. Puedes pasar directamente a la firma del contrato."
        )
        b1, b2 = st.columns(2)
        with b1:
            if st.button(
                "Continuar a firma del contrato",
                type="primary",
                use_container_width=True,
                key="ctsig_s3_empty_go_sign",
            ):
                _advance_to_contract_signature_step_after_payment_check(appointment_id)
        with b2:
            if st.button("Volver al panel principal", use_container_width=True, key="ctsig_s3_empty"):
                _panel_principal_from_step3()
        return

    st.markdown("Completa el siguiente formulario.")

    @st.fragment
    def _fragment_ctsig_survey_form() -> None:
        st.markdown('<div class="ctsig-survey-root" aria-hidden="true"></div>', unsafe_allow_html=True)
        for row_start in range(0, len(qs), 2):
            col_left, col_right = st.columns(2, gap="large")
            with col_left:
                _render_contract_survey_question(qs[row_start])
            with col_right:
                if row_start + 1 < len(qs):
                    _render_contract_survey_question(qs[row_start + 1])
            st.divider()

        st.selectbox(
            "¿Recomendaría nuestros servicios?",
            options=[_CTSIG_Q_UNSET, "Sí", "No"],
            format_func=_fmt_survey_no_selection,
            key="ctsig_s3_would_rec",
        )
        if st.button("Enviar cuestionario", type="primary", use_container_width=True, key="ctsig_s3_submit"):
            _submit_ctsig_survey(appointment_id, qs)

    _fragment_ctsig_survey_form()

    nav_q1, nav_q2 = st.columns(2)
    with nav_q1:
        if st.button("← Volver a datos personales", use_container_width=True, key="ctsig_q_back"):
            st.session_state["ctsig_step"] = 1
            st.rerun()
    with nav_q2:
        if st.button("Volver al panel principal", use_container_width=True, key="ctsig_s3_done"):
            _panel_principal_from_step3()


def _render_step3_artist_only_signature(
    appointment_id: int,
    appointment: dict[str, Any],
) -> None:
    """Solo lienzo del profesional: sin datos del cliente, sin texto del contrato ni encuesta."""
    st.markdown("#### Tu firma en el contrato")
    st.caption(
        "Recepción ya registró el contrato y la firma del cliente. "
        "Solo debes dibujar tu firma abajo; no verás datos personales ni encuesta."
    )
    ok_pay, pay_err = _appointment_payment_ready_for_signature(appointment)
    if not ok_pay:
        st.error(pay_err or "Completa el abono antes de registrar la firma.")
        return

    ok_s, code_s, summary = api_client.get_contract_latest_summary_for_appointment(int(appointment_id))
    if not ok_s or not isinstance(summary, dict):
        st.error(f"No se pudo verificar el contrato (HTTP {code_s}): {_detail(summary)}")
        return
    if not summary.get("pending_artist_signature"):
        st.success("Este contrato ya tiene la firma del profesional.")
        if st.button("Volver al panel principal", type="primary", key="ctsig_ao_already"):
            _exit_contract_signing_to_panel()
        return

    _sig_w, _sig_h = 340, 170
    artist_signature = _signature_pad_b64(
        "Firma del tatuador/perforador *",
        "ctsig_artist_only_pad",
        canvas_width=_sig_w,
        canvas_height=_sig_h,
    )

    b1, b2 = st.columns(2)
    with b1:
        if st.button("← Volver al panel principal", use_container_width=True, key="ctsig_ao_cancel"):
            _exit_contract_signing_to_panel()
    with b2:
        if st.button(
            "Guardar firma profesional",
            type="primary",
            use_container_width=True,
            key="ctsig_ao_save",
        ):
            if not _signature_payload_acceptable(artist_signature):
                st.warning("Dibuja tu firma en el recuadro antes de guardar.")
            else:
                payload = {
                    "appointment_id": int(appointment_id),
                    "artist_signature": artist_signature,
                }
                ok_p, code_p, data_p = api_client.post_contract_complete_artist_signature(payload)
                if ok_p:
                    _request_citas_list_refresh()
                    st.session_state["_panel_pending_toast"] = (
                        "Firma del profesional registrada; la cita quedó finalizada."
                    )
                    _exit_contract_signing_to_panel()
                else:
                    st.error(f"No se pudo guardar (HTTP {code_p}): {_detail(data_p)}")


def render_contract_signing_view(appointment_id: int) -> None:
    aid = int(appointment_id)
    artist_only_q = _contract_artist_only_query()
    if st.session_state.get("ctsig_aid") != aid:
        st.session_state["ctsig_aid"] = aid
        skip_init = bool(st.session_state.pop("ctsig_skip_init_step", False))
        if artist_only_q:
            st.session_state["ctsig_step"] = 3
            st.session_state["ctsig_artist_only"] = True
        else:
            st.session_state["ctsig_step"] = 2 if skip_init else 1
            st.session_state.pop("ctsig_artist_only", None)
        st.session_state.pop("_ctsig_pending_toast", None)
        _ctsig_clear_contract_caches()

    step = int(st.session_state.get("ctsig_step", 1))
    if st.session_state.get("ctsig_artist_only") or artist_only_q:
        step = 3
        st.session_state["ctsig_step"] = 3
        st.session_state["ctsig_artist_only"] = True
    if step not in (1, 2, 3):
        step = 1
        st.session_state["ctsig_step"] = 1

    ok_a, code_a, appt = api_client.get_appointment(aid)
    if not ok_a or not isinstance(appt, dict):
        st.error(f"No se pudo cargar la cita (HTTP {code_a}): {_detail(appt)}")
        return

    if int(appt.get("id", 0) or 0) != aid:
        st.error("Cita no encontrada.")
        return

    tech = _panel_session_is_technician()
    pending_professional = bool(appt.get("contract_pending_artist_signature"))
    if tech and pending_professional:
        st.session_state["ctsig_artist_only"] = True
        st.session_state["ctsig_step"] = 3

    artist_only_ui = bool(st.session_state.get("ctsig_artist_only"))

    if tech and not pending_professional and not artist_only_ui:
        st.subheader("Firma de contrato")
        st.caption("Tu perfil solo permite completar **tu firma** cuando recepción ya registró el contrato del cliente.")
        if st.button("Volver al panel principal", key="ctsig_back"):
            _exit_contract_signing_to_panel()
        st.warning(
            "La **firma del cliente** y la **encuesta** las gestiona **recepción**. "
            "Cuando falte tu firma, en **Gestión de citas** verás el botón **Completar firma profesional**."
        )
        return

    if artist_only_ui:
        st.subheader("Firma profesional")
        st.caption("Solo registro de tu firma; sin datos del cliente ni encuesta.")
    else:
        st.subheader("Firma digital de contrato")
        _steps_progress(step)

    if st.button("Volver al panel principal", key="ctsig_back"):
        _exit_contract_signing_to_panel()

    pending_flow = st.session_state.pop("_ctsig_pending_toast", None)
    if pending_flow:
        _toast_ok(str(pending_flow))
    if artist_only_ui or st.session_state.get("ctsig_artist_only"):
        st.caption(f"Cita **#{aid}** · Servicio: **{appt.get('service_type', '—')}**")
    else:
        st.caption(
            f"Cita **#{aid}** · Artista: **{_appointment_artist_display_name(appt)}** · "
            f"Servicio: **{appt.get('service_type', '—')}** · Cliente: **{appt.get('customer_name', '—')}**"
        )
    if not service_type_requires_contract(appt.get("service_type")):
        st.info(
            "Las citas de tipo **Cambio** o **Limpieza** no requieren firma de contrato digital."
        )
        st.caption(f"Servicio registrado: `{appt.get('service_type', '—')}`")
        if st.button("Volver al panel principal", type="primary", key="ctsig_no_contract_back"):
            _exit_contract_signing_to_panel()
        return
    if st.session_state.get("ctsig_artist_only"):
        if not bool(appt.get("contract_pending_artist_signature")):
            st.warning(
                "Esta vista es solo para completar la **firma del profesional**. "
                "Aquí no aplica (el contrato ya está completo o el cliente aún no ha firmado)."
            )
            if st.button("Volver al panel principal", type="primary", key="ctsig_ao_nop"):
                _exit_contract_signing_to_panel()
            return
        _render_step3_artist_only_signature(aid, appt)
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
        _render_step1_personal(customer_id, customer, appt)
        return
    if step == 2:
        _render_step2_questionnaire(aid, appt)
        return
    _render_step3_sign_contract(aid, customer_id, customer, appt)


def _leave_express_piercing_to_panel() -> None:
    for k in list(st.session_state.keys()):
        if isinstance(k, str) and k.startswith("ctsig_expr_"):
            st.session_state.pop(k, None)
    st.session_state.pop("ctsig_skip_init_step", None)
    st.session_state.pop("ctsig_artist_only", None)
    leave_contract_view_to_panel()


def _format_cop_express(value: float | int) -> str:
    amount = int(round(float(value or 0)))
    return f"COP ${amount:,.0f}".replace(",", ".")


def render_contract_express_piercing_view() -> None:
    """Flujo piercing: agenda → alta cliente (POST) → cita (POST) → misma vista de firma (pasos 2 y 3)."""
    from streamlit_app.appointment_agenda_slots import (
        MAX_BOOKING_DURATION_SLOTS as _MAX_BOOKING_DURATION_SLOTS,
        MIN_BOOKING_DURATION_SLOTS as _MIN_BOOKING_DURATION_SLOTS,
        append_agenda_slots_marker as _append_agenda_slots_marker,
    )
    from streamlit_app.appointment_dates import combine_appointment_datetime as _combine_appointment_datetime
    from streamlit_app.appointment_slots import (
        available_start_slots as _available_start_slots,
        busy_slot_indices_for_day as _busy_slot_indices_for_day,
        time_slot_options as _time_slot_options,
    )
    from streamlit_app.citas_agendar_helpers import (
        initial_receipt_success_message as _initial_receipt_success_message,
        show_validation_errors as _show_validation_errors,
    )
    from streamlit_app.citas_agendar_state import queue_appointment_action_success as _queue_appointment_action_success
    from streamlit_app.citas_booking_meta import (
        service_and_detail_for_work_kind as _service_and_detail_for_work_kind,
        work_kind_to_assignee_role as _work_kind_to_assignee_role,
        work_kind_to_schedule_kind as _work_kind_to_schedule_kind,
    )
    from streamlit_app.citas_panel_staff import ensure_assignable_staff as _ensure_assignable_staff
    from streamlit_app.citas_schedule_queries import (
        appointments_for_artist_schedule as _appointments_for_artist_schedule,
        appointments_same_day_schedule_kind as _appointments_same_day_schedule_kind,
    )
    from streamlit_app.citas_agendar_sections import render_agendar_required_banner_html
    from streamlit_app.panel_auth import panel_auth_enabled

    st.subheader("Cita express (piercing)")
    st.caption(
        "Agenda la cita con **abono completo**, registra los **datos del cliente** y continúa con la **encuesta** "
        "y la **firma del contrato** en el mismo asistente."
    )
    if st.button("Volver al panel principal", key="ctsig_expr_back_panel"):
        _leave_express_piercing_to_panel()
        return

    if _panel_session_is_technician():
        st.warning(
            "Tu rol (**tatuador** / **perforador**) no puede iniciar citas express desde aquí. "
            "Pide a recepción que registre la cita o usa una cuenta con permiso de agenda."
        )
        return

    booking = st.session_state.get("ctsig_expr_booking")
    if not isinstance(booking, dict):
        st.markdown("#### Datos de la cita")
        st.info(
            "Define día, perforador, horario y montos. **El valor total debe quedar cubierto por el abono** "
            "para pasar al cuestionario y a la firma."
        )
        render_agendar_required_banner_html()
        st.caption("**Piercing (cita express)** — misma disposición que al agendar desde el calendario.")

        wk_submit = "piercing"
        need_role = _work_kind_to_assignee_role(wk_submit)

        c_fecha, c_prof = st.columns(2)
        with c_fecha:
            st.markdown('<p class="dlg-appt-col-h">Fecha de la cita</p>', unsafe_allow_html=True)
            picked_raw = st.session_state.get("ctsig_expr_pick_day")
            picked = picked_raw if isinstance(picked_raw, date) else date.today()
            st.date_input(
                "Día en agenda *",
                value=picked,
                min_value=date.today(),
                format="DD/MM/YYYY",
                key="ctsig_expr_pick_day",
                label_visibility="collapsed",
            )
        picked2_raw = st.session_state.get("ctsig_expr_pick_day")
        picked_d = picked2_raw if isinstance(picked2_raw, date) else date.today()

        assigned_id: Optional[int] = None
        with c_prof:
            st.markdown('<p class="dlg-appt-col-h">Profesional asignado</p>', unsafe_allow_html=True)
            staff_opts = [s for s in _ensure_assignable_staff() if str(s.get("role")) == need_role]
            role_me = str(st.session_state.get("_panel_user_role") or "")
            uid_me = st.session_state.get("_panel_user_id")
            locked_self = (
                panel_auth_enabled()
                and not st.session_state.get("_panel_session_full_access")
                and role_me == need_role
                and uid_me is not None
            )
            if locked_self:
                assigned_id = int(uid_me)
                st.caption("La cita quedará asignada a **tu usuario** del panel.")
            elif not staff_opts:
                st.error(
                    f"No hay usuario activo con rol **{need_role}**. "
                    "Da de alta un perforador en **Gestión de usuarios**."
                )
            else:
                labels_p = [
                    f"{s.get('first_name', '')} {s.get('last_name', '')} (@{s.get('username', '')})"
                    for s in staff_opts
                ]
                pick_key = "ctsig_expr_staff_pick"
                if pick_key not in st.session_state or st.session_state[pick_key] not in labels_p:
                    st.session_state[pick_key] = labels_p[0]
                choice_p = st.selectbox(
                    "Perforador *",
                    options=labels_p,
                    key=pick_key,
                    label_visibility="collapsed",
                )
                idx_p = labels_p.index(str(choice_p))
                assigned_id = int(staff_opts[idx_p]["id"])

        c_dur, c_hr = st.columns(2)
        with c_dur:
            st.markdown('<p class="dlg-appt-col-h">Duración en agenda</p>', unsafe_allow_html=True)
            st.number_input(
                "Franjas de 30 min *",
                min_value=_MIN_BOOKING_DURATION_SLOTS,
                max_value=_MAX_BOOKING_DURATION_SLOTS,
                step=1,
                key="ctsig_expr_slots",
                label_visibility="collapsed",
            )
        need_slots = max(
            _MIN_BOOKING_DURATION_SLOTS,
            min(_MAX_BOOKING_DURATION_SLOTS, int(st.session_state.get("ctsig_expr_slots") or 1)),
        )
        slot_opts = _time_slot_options()
        sched_kind = _work_kind_to_schedule_kind(wk_submit)
        raw_appt_list = list(st.session_state.get("_ap_list") or [])
        artist_for_busy: Optional[int] = None
        aid_raw = assigned_id
        if aid_raw not in (None, "", 0):
            try:
                artist_for_busy = int(aid_raw)
            except (TypeError, ValueError):
                artist_for_busy = None
        if artist_for_busy is not None:
            day_rows_cal = _appointments_for_artist_schedule(
                raw_appt_list, picked_d, artist_for_busy, schedule_kind=sched_kind
            )
        else:
            day_rows_cal = _appointments_same_day_schedule_kind(raw_appt_list, picked_d, sched_kind)
        busy_idx = _busy_slot_indices_for_day(day_rows_cal, slot_opts)
        avail_slots = _available_start_slots(slot_opts, need_slots, busy_idx)
        cur_slot = st.session_state.get("ctsig_expr_slot")
        if avail_slots and cur_slot not in avail_slots:
            st.session_state["ctsig_expr_slot"] = avail_slots[0]

        slot: Optional[str]
        with c_hr:
            st.markdown('<p class="dlg-appt-col-h">Hora de inicio</p>', unsafe_allow_html=True)
            if not avail_slots:
                st.warning(
                    "No quedan franjas libres ese día para esta duración. Prueba otro día o revisa las citas ya cargadas."
                )
                slot = None
            else:
                slot = st.selectbox(
                    "Franja de inicio *",
                    options=avail_slots,
                    key="ctsig_expr_slot",
                    label_visibility="collapsed",
                )
                slot_vis = str(st.session_state.get("ctsig_expr_slot") or "").strip()
                st.caption(f"Inicio **{slot_vis or '—'}** · duración **{need_slots * 30}** min")

        st.markdown(f"**Fecha de la cita:** {picked_d.strftime('%d/%m/%Y')}")

        st.markdown('<p class="dlg-appt-col-h">Cita y montos</p>', unsafe_allow_html=True)
        cm1, cm2 = st.columns(2)
        with cm1:
            st.text_area(
                "Notas u observaciones (opcional)",
                height=68,
                key="ctsig_expr_det",
            )
            st.checkbox(
                "Cita prioritaria",
                key="ctsig_expr_priority",
            )
        with cm2:
            st.number_input(
                "Valor total del trabajo (COP) *",
                min_value=0.0,
                step=10000.0,
                format="%.0f",
                key="ctsig_expr_total",
            )
            st.number_input(
                "Saldo abonado (COP) *",
                min_value=0.0,
                step=10000.0,
                format="%.0f",
                key="ctsig_expr_dep",
            )
            total_amount = float(st.session_state.get("ctsig_expr_total") or 0)
            deposit = max(0.0, round(float(st.session_state.get("ctsig_expr_dep") or 0), 2))
            pending_balance = round(total_amount - deposit, 2)
            st.caption(
                f"Saldo pendiente: **{_format_cop_express(max(pending_balance, 0))}** "
                "(debe ser **0** para encuesta y firma)."
            )

        c_go, c_cancel = st.columns(2)
        with c_cancel:
            if st.button("Cancelar", use_container_width=True, key="ctsig_expr_book_cancel"):
                _leave_express_piercing_to_panel()
        with c_go:
            if st.button("Continuar a datos del cliente", type="primary", use_container_width=True, key="ctsig_expr_book_go"):
                if assigned_id is None:
                    st.error("Indica el perforador asignado.")
                    return
                if picked_d < date.today():
                    st.error("La fecha no puede ser anterior a hoy.")
                    return
                if not avail_slots or slot is None:
                    st.error("No hay franja disponible.")
                    return
                if total_amount <= 0:
                    st.error("Indica un valor total mayor a cero.")
                    return
                if round(total_amount - deposit, 2) > 0.02:
                    st.error(
                        "Para pasar a **encuesta y firma**, el **abono debe cubrir el valor total** de la cita "
                        "(saldo pendiente cero)."
                    )
                    return
                slot_str = (st.session_state.get("ctsig_expr_slot") or "").strip()
                aid_int = int(assigned_id)
                slot_opts_chk = _time_slot_options()
                raw_chk = list(st.session_state.get("_ap_list") or [])
                day_chk = _appointments_for_artist_schedule(
                    raw_chk, picked_d, aid_int, schedule_kind=sched_kind
                )
                busy_chk = _busy_slot_indices_for_day(day_chk, slot_opts_chk)
                avail_chk = _available_start_slots(slot_opts_chk, need_slots, busy_chk)
                if not avail_chk or slot_str not in avail_chk:
                    st.error("La franja ya no está libre. Elige otra hora.")
                    return
                detail_raw = str(st.session_state.get("ctsig_expr_det") or "")
                service, detail_for_api = _service_and_detail_for_work_kind(wk_submit, detail_raw)
                detail_for_api = _append_agenda_slots_marker(detail_for_api or "", need_slots)
                st.session_state["ctsig_expr_booking"] = {
                    "picked": picked_d,
                    "slot_str": slot_str,
                    "assigned_id": aid_int,
                    "duration_slots": need_slots,
                    "total": float(total_amount),
                    "deposit": float(deposit),
                    "service": service,
                    "detail": detail_for_api,
                    "priority": bool(st.session_state.get("ctsig_expr_priority")),
                }
                st.rerun()
        return

    # --- Fase datos cliente + crear registros ---
    bk = booking
    st.markdown("#### Datos personales del cliente")
    st.caption(
        "Completa la ficha. Se creará el **cliente** y la **cita**; después entrarás en **cuestionario** y **firma**."
    )
    if st.button("← Volver a agenda", key="ctsig_expr_back_booking"):
        st.session_state.pop("ctsig_expr_booking", None)
        st.rerun()

    min_date_100, max_date_today = _date_range_100y()
    ed: dict[str, Any] = {}
    a, b = st.columns(2)
    with a:
        st.text_input("Nombre *", value=str(ed.get("first_name") or ""), key="ctsig_expr_s1_fn")
        st.text_input("Apellido *", value=str(ed.get("last_name") or ""), key="ctsig_expr_s1_ln")
        bd_raw = st.date_input(
            "Fecha de nacimiento *",
            value=_clamp_date(_parse_date(ed.get("birth_date")), min_date_100, max_date_today),
            min_value=min_date_100,
            max_value=max_date_today,
            key="ctsig_expr_s1_bd",
            format="DD/MM/YYYY",
        )
        bd = bd_raw if isinstance(bd_raw, date) else _parse_date(bd_raw)
        if bd != CUSTOMER_BIRTH_PENDING and _is_minor_by_birth_date(bd):
            st.warning(
                "**Menor de edad:** en la **etapa de firma** completarás datos del tutor o representante "
                "y la documentación requerida antes de guardar el contrato."
            )
        edt = st.selectbox(
            "Tipo de documento *",
            ["CC", "TI", "CE", "PAS"],
            index=_doc_type_index(ed.get("document_type")),
            format_func=lambda x: {"CC": "CC — Cédula", "TI": "TI — Tarjeta identidad", "CE": "CE — Extranjería", "PAS": "PAS — Pasaporte"}[x],
            key="ctsig_expr_s1_dt",
        )
        st.text_input("Número de documento *", value=str(ed.get("document_number") or ""), key="ctsig_expr_s1_dn")
        eddi_raw = ed.get("document_issue_date")
        st.checkbox(
            "Registrar fecha de expedición del documento del cliente *",
            value=bool(eddi_raw),
            key="ctsig_expr_s1_has_ddi",
            help="Para firmar el contrato desde el panel es obligatorio indicar la expedición del documento.",
        )
        st.date_input(
            "Fecha de expedición del documento del cliente",
            value=_clamp_date(_parse_date(eddi_raw), min_date_100, max_date_today) if eddi_raw else date(2015, 1, 1),
            min_value=min_date_100,
            max_value=max_date_today,
            key="ctsig_expr_s1_ddi",
            format="DD/MM/YYYY",
        )
    with b:
        st.text_input("Correo *", value=str(ed.get("email") or ""), key="ctsig_expr_s1_em")
        st.text_input(
            "Celular *",
            value=str(ed.get("phone_number") or ""),
            key="ctsig_expr_s1_ph",
            help="10 dígitos (puedes escribir espacios o +57; se validan solo los dígitos).",
        )
        st.text_input(
            "Nacionalidad *",
            value=str(ed.get("nationality") or ""),
            key="ctsig_expr_s1_nat",
        )
        st.text_input(
            "Profesión *",
            value=str(ed.get("profession") or ""),
            key="ctsig_expr_s1_prof",
        )

    with st.expander("Contacto y redes (obligatorio para firma)", expanded=True):
        st.text_input("Dirección *", value=str(ed.get("address") or ""), key="ctsig_expr_s1_addr")
        st.text_area(
            "Redes sociales *",
            value=social_media_api_to_form_text(ed.get("social_media")),
            height=70,
            key="ctsig_expr_s1_sm",
            max_chars=SOCIAL_MEDIA_MAX_LEN,
            help=f"Texto plano, máximo {SOCIAL_MEDIA_MAX_LEN} caracteres (@, enlaces, etc.). No es JSON.",
        )

    with st.expander("Contacto de emergencia (obligatorio para firma)", expanded=True):
        st.text_input("Nombre contacto emergencia *", value=str(ed.get("emergency_contact_name") or ""), key="ctsig_expr_s1_ecn")
        st.text_input(
            "Celular contacto emergencia *",
            value=str(ed.get("emergency_contact_phone") or ""),
            key="ctsig_expr_s1_ecp",
            help="10 dígitos (obligatorio para firmar desde esta vista).",
        )

    if st.button("Crear cliente y cita, ir al cuestionario", type="primary", use_container_width=True, key="ctsig_expr_submit"):
        picked_d = bk["picked"]
        slot_str = str(bk["slot_str"] or "").strip()
        aid_int = int(bk["assigned_id"])
        service = str(bk["service"] or "")
        detail_for_api = bk.get("detail")
        tot = float(bk["total"])
        dep = float(bk["deposit"])
        fn = (st.session_state.get("ctsig_expr_s1_fn") or "").strip()
        ln = (st.session_state.get("ctsig_expr_s1_ln") or "").strip()
        if len(fn) < 1 or len(ln) < 1:
            st.error("Nombre y apellido son obligatorios.")
            return
        bd_v = st.session_state.get("ctsig_expr_s1_bd")
        if not isinstance(bd_v, date):
            bd_v = _parse_date(bd_v) if bd_v not in (None, "") else None
        if bd_v is None:
            st.error("La **fecha de nacimiento** es obligatoria.")
            return
        if bd_v == CUSTOMER_BIRTH_PENDING:
            st.error(
                "Indica la **fecha de nacimiento real** del cliente (no la fecha provisional del agendamiento)."
            )
            return
        expected_minor = _is_minor_by_birth_date(bd_v)
        dt = str(st.session_state.get("ctsig_expr_s1_dt") or "CC")
        dn = (st.session_state.get("ctsig_expr_s1_dn") or "").strip()
        if len(dn) < 5:
            st.error("Número de documento inválido.")
            return
        has_ddi = bool(st.session_state.get("ctsig_expr_s1_has_ddi"))
        if not has_ddi:
            st.error(
                "Para firmar el contrato debes marcar **Registrar fecha de expedición del documento** "
                "e indicar la fecha correcta."
            )
            return
        ddi_v = st.session_state.get("ctsig_expr_s1_ddi")
        if not isinstance(ddi_v, date):
            ddi_v = _parse_date(ddi_v)
        doc_err = _validate_document_rules(
            birth_date=bd_v,
            document_type=dt,
            has_document_issue_date=True,
            document_issue_date=ddi_v,
        )
        if doc_err:
            st.error(doc_err)
            return
        em = (st.session_state.get("ctsig_expr_s1_em") or "").strip()
        ph = (st.session_state.get("ctsig_expr_s1_ph") or "").strip()
        if len(em) < 3:
            st.error("El correo es obligatorio (formato válido).")
            return
        ph_err = mobile_phone_co_10_error(ph)
        if ph_err:
            st.error(ph_err)
            return
        nat = (st.session_state.get("ctsig_expr_s1_nat") or "").strip()
        if len(nat) < 2:
            st.error("La **nacionalidad** es obligatoria para firmar el contrato.")
            return
        prof = (st.session_state.get("ctsig_expr_s1_prof") or "").strip()
        if len(prof) < 2:
            st.error("La **profesión** es obligatoria para firmar el contrato.")
            return
        addr = (st.session_state.get("ctsig_expr_s1_addr") or "").strip()
        if len(addr) < 5:
            st.error("La **dirección** es obligatoria para firmar el contrato (al menos 5 caracteres).")
            return
        sm_raw = st.session_state.get("ctsig_expr_s1_sm") or ""
        sm_err = social_media_text_error(str(sm_raw))
        if sm_err:
            st.error(sm_err)
            return
        sm_for_api = social_media_form_text_to_api(str(sm_raw))
        if not sm_for_api:
            st.error("Indica **redes sociales** (texto breve: usuario @, red o enlace).")
            return
        ecn = (st.session_state.get("ctsig_expr_s1_ecn") or "").strip()
        if len(ecn) < 3:
            st.error("El **nombre del contacto de emergencia** es obligatorio.")
            return
        ecp = (st.session_state.get("ctsig_expr_s1_ecp") or "").strip()
        ecp_err = mobile_phone_co_10_error(ecp)
        if ecp_err:
            st.error(f"Celular de emergencia: {ecp_err}")
            return

        full_name = f"{fn} {ln}".strip()
        dt_str = _combine_appointment_datetime(picked_d, slot_str)
        detail_raw_val = str(bk.get("detail") or "")
        valid_a, errs_a = validate_appointment(full_name, ph, em, service, dt_str, detail_raw_val, dep)
        if not valid_a:
            _show_validation_errors(errs_a)
            return
        if dep > tot:
            st.error("El saldo abonado no puede ser mayor que el valor total.")
            return

        try:
            c_new = CustomerCreate(
                first_name=fn,
                last_name=ln,
                birth_date=bd_v,
                document_type=dt,  # type: ignore[arg-type]
                document_number=dn,
                document_issue_date=ddi_v,
                email=em,
                phone_number=ph,
                address=addr or None,
                nationality=nat or None,
                profession=prof or None,
                social_media=sm_for_api,
                emergency_contact_name=ecn or None,
                emergency_contact_phone=ecp or None,
                is_minor=expected_minor,
            )
        except ValidationError as ve:
            st.error(str(ve))
            return

        cust_payload = c_new.model_dump(mode="json")
        with st.spinner("Creando cliente…"):
            ok_c, code_c, data_c = api_client.post_customer(cust_payload)
        if not ok_c or not isinstance(data_c, dict):
            st.error(f"No se pudo crear el cliente (HTTP {code_c}): {_detail(data_c)}")
            return
        cid_raw = data_c.get("id")
        if cid_raw is None:
            st.error("Respuesta de alta de cliente sin id.")
            return
        customer_id = int(cid_raw)

        pending_bal = max(round(float(tot) - float(dep), 2), 0)
        appt_payload: dict[str, Any] = {
            "name": full_name,
            "phone": ph,
            "service": service,
            "date": dt_str,
            "detail": detail_for_api,
            "deposit": float(dep),
            "total_amount": float(tot),
            "pending_balance": float(pending_bal),
            "is_priority": bool(bk.get("priority")),
            "assigned_panel_user_id": aid_int,
            "customer_id": customer_id,
        }
        with st.spinner("Creando cita…"):
            ok_a, code_a, data_a = api_client.post_appointment(appt_payload)
        if not ok_a or not isinstance(data_a, dict):
            st.error(f"No se pudo crear la cita (HTTP {code_a}): {_detail(data_a)}")
            return
        aid_new_raw = data_a.get("id")
        if aid_new_raw is None:
            st.error("Respuesta de cita sin id.")
            return
        aid_new = int(aid_new_raw)

        st.session_state["_ap_reload"] = True
        dep_created = max(0.0, round(float(dep), 2))
        _queue_appointment_action_success(_initial_receipt_success_message(dep_created, str(service)))
        st.session_state.pop("ctsig_expr_booking", None)
        for k in list(st.session_state.keys()):
            if isinstance(k, str) and k.startswith("ctsig_expr_s1_"):
                st.session_state.pop(k, None)
        st.session_state["ctsig_skip_init_step"] = True
        st.query_params["appointment_id"] = str(aid_new)
        st.query_params.pop("express_piercing", None)
        st.rerun()
