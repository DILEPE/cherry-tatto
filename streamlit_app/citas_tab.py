"""Streamlit: Citas tab with customer sync before appointment creation."""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import streamlit as st

from app.domain.service_types import configured_service_types
from streamlit_app import api_client
from streamlit_app.customer_sync import fetch_customer_by_document, parse_social_media_json, sync_customer
from streamlit_app.validation import validate_appointment


def _api_error(payload: Any) -> str:
    if isinstance(payload, dict):
        return str(payload.get("detail", payload))
    return str(payload)


def _show_validation_errors(errors: List[Any]) -> None:
    for e in errors:
        st.markdown(
            f'<div class="m-error"><strong>{e.field}</strong>: {e.message}</div>',
            unsafe_allow_html=True,
        )


def _format_cop(value: float | int) -> str:
    amount = int(round(float(value or 0)))
    return f"COP ${amount:,.0f}".replace(",", ".")


def _parse_date(val: Any) -> date:
    if isinstance(val, date):
        return val
    if isinstance(val, str) and val:
        return datetime.strptime(val[:10], "%Y-%m-%d").date()
    return date(1990, 1, 1)


def _social_to_text(row: Optional[Dict[str, Any]]) -> str:
    if not row or not row.get("social_media"):
        return ""
    sm = row["social_media"]
    if isinstance(sm, str):
        return sm
    try:
        return json.dumps(sm, ensure_ascii=False)
    except (TypeError, ValueError):
        return ""


def _apply_customer_row_to_session(row: Dict[str, Any]) -> None:
    """
    Copia un cliente de la API al st.session_state de los widgets.
    Debe llamarse al **inicio** de la app, **antes** de instanciar widgets con esas claves
    (p. ej. tras un st.rerun() que encola el resultado de «Buscar por documento»).
    """
    st.session_state["ap_doc_t"] = row.get("document_type") or "CC"
    st.session_state["ap_doc_n"] = (row.get("document_number") or "").strip()
    st.session_state["ap_fn"] = (row.get("first_name") or "").strip()
    st.session_state["ap_ln"] = (row.get("last_name") or "").strip()
    st.session_state["ap_bd"] = _parse_date(row.get("birth_date"))
    st.session_state["ap_em"] = (row.get("email") or "").strip()
    st.session_state["ap_addr"] = (row.get("address") or "").strip() or ""
    st.session_state["ap_nat"] = (row.get("nationality") or "").strip() or ""
    st.session_state["ap_prof"] = (row.get("profession") or "").strip() or ""
    st.session_state["ap_se"] = (row.get("secondary_email") or "").strip() or ""
    st.session_state["ap_sm"] = _social_to_text(row)
    st.session_state["ap_ecn"] = (row.get("emergency_contact_name") or "").strip() or ""
    st.session_state["ap_ecp"] = (row.get("emergency_contact_phone") or "").strip() or ""
    st.session_state["ap_minor"] = bool(row.get("is_minor"))
    st.session_state["ap_gn"] = (row.get("guardian_name") or "").strip() or ""
    gtype = (row.get("guardian_document_type") or "CC")
    st.session_state["ap_gdt"] = gtype if gtype in ("CC", "TI", "CE", "PAS") else "CC"
    st.session_state["ap_gdn"] = (row.get("guardian_document_number") or "").strip() or ""
    gdiv = row.get("guardian_document_issue_date")
    st.session_state["ap_gdi"] = _parse_date(gdiv) if gdiv else date(2000, 1, 1)
    st.session_state["ap_phone"] = (row.get("phone_number") or "").strip()
    st.session_state["_ap_last_loaded_id"] = row.get("id")
    st.session_state["_ap_prefill_meta"] = (
        f"{st.session_state['ap_fn']} {st.session_state['ap_ln']}".strip()
    )


def _reset_customer_fields_keep_doc(doc_keep: str) -> None:
    """Vaciar datos de cliente al no existir documento, manteniendo el número buscado."""
    st.session_state["ap_fn"] = ""
    st.session_state["ap_ln"] = ""
    st.session_state["ap_bd"] = date(1990, 1, 1)
    st.session_state["ap_em"] = ""
    st.session_state["ap_addr"] = ""
    st.session_state["ap_nat"] = ""
    st.session_state["ap_prof"] = ""
    st.session_state["ap_se"] = ""
    st.session_state["ap_sm"] = ""
    st.session_state["ap_ecn"] = ""
    st.session_state["ap_ecp"] = ""
    st.session_state["ap_minor"] = False
    st.session_state["ap_gn"] = ""
    st.session_state["ap_gdt"] = "CC"
    st.session_state["ap_gdn"] = ""
    st.session_state["ap_gdi"] = date(2000, 1, 1)
    st.session_state["ap_phone"] = ""
    st.session_state["ap_doc_t"] = "CC"
    st.session_state["ap_doc_n"] = doc_keep
    st.session_state["_ap_prefill_meta"] = None
    st.session_state["_ap_last_loaded_id"] = None


def _init_appt_form_state_once() -> None:
    """Valores iniciales solo la primera vez (hasta `st.rerun` típico)."""
    if st.session_state.get("_ap_form_ready"):
        return
    defaults: Dict[str, Any] = {
        "ap_doc_t": "CC",
        "ap_doc_n": "",
        "ap_fn": "",
        "ap_ln": "",
        "ap_bd": date(1990, 1, 1),
        "ap_em": "",
        "ap_addr": "",
        "ap_nat": "",
        "ap_prof": "",
        "ap_se": "",
        "ap_sm": "",
        "ap_ecn": "",
        "ap_ecp": "",
        "ap_minor": False,
        "ap_gn": "",
        "ap_gdt": "CC",
        "ap_gdn": "",
        "ap_gdi": date(2000, 1, 1),
        "ap_phone": "",
        "ap_ad": date.today(),
        "ap_det": "",
        "ap_dep": 0.0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    svc = list(configured_service_types())
    st.session_state["ap_svc"] = svc[0] if svc else "tattoo"
    st.session_state["_ap_form_ready"] = True
    st.session_state["_ap_prefill_meta"] = None
    st.session_state["_ap_last_loaded_id"] = None


def _process_pending_lookup() -> None:
    """
    Aplica búsqueda de cliente en la siguiente ejecución, **antes** de crear widgets,
    para poder escribir en st.session_state sin violar reglas de Streamlit.
    """
    pending = st.session_state.pop("_ap_pending_lookup", None)
    if not isinstance(pending, dict):
        return
    action = pending.get("action")
    if action == "apply" and pending.get("row"):
        _apply_customer_row_to_session(pending["row"])
        st.session_state["_ap_flash"] = (
            "success",
            "Datos del cliente existente cargados en el formulario.",
        )
    elif action == "not_found" and pending.get("doc") is not None:
        _reset_customer_fields_keep_doc(str(pending["doc"]).strip())
        st.session_state["_ap_flash"] = (
            "warning",
            "No hay cliente con ese documento. Completa los datos; se creará al guardar la cita.",
        )


def render_citas_tab() -> None:
    _init_appt_form_state_once()
    _process_pending_lookup()

    with st.expander("Nueva cita", expanded=True):
        fl = st.session_state.pop("_ap_flash", None)
        if fl and len(fl) == 2:
            if fl[0] == "success":
                st.success(fl[1])
            elif fl[0] == "warning":
                st.warning(fl[1])
            else:
                st.info(fl[1])

        st.markdown("##### Datos del cliente (obligatorios para vincular la cita)")
        d1, d2, d3 = st.columns(3)
        with d1:
            doc_type = st.selectbox(
                "Tipo documento *",
                ["CC", "TI", "CE", "PAS"],
                key="ap_doc_t",
                format_func=lambda x: {
                    "CC": "CC — Cédula",
                    "TI": "TI — Tarjeta identidad",
                    "CE": "CE — Extranjería",
                    "PAS": "PAS — Pasaporte",
                }[x],
            )
            doc_number = st.text_input("Número documento *", key="ap_doc_n", placeholder="Sin espacios")
        with d2:
            if st.button("Buscar por documento", type="primary", key="ap_doc_lookup"):
                doc = (st.session_state.get("ap_doc_n") or "").strip()
                if not doc or len(doc) < 3:
                    st.error("Escribe un número de documento válido (mín. 3 caracteres).")
                else:
                    ok, msg, row = fetch_customer_by_document(doc)
                    if ok and msg == "ok" and row:
                        st.session_state["_ap_pending_lookup"] = {"action": "apply", "row": row}
                        st.rerun()
                    elif ok and msg == "not_found":
                        st.session_state["_ap_pending_lookup"] = {"action": "not_found", "doc": doc}
                        st.rerun()
                    else:
                        st.error(msg)
        with d3:
            st.caption("Pulsa *Buscar por documento* para rellenar con datos de la **base de clientes**.")
            if st.session_state.get("_ap_prefill_meta") or st.session_state.get("_ap_last_loaded_id"):
                st.info(
                    f"Cliente en formulario: **{st.session_state.get('_ap_prefill_meta', '—')}**  "
                    f"(ID: {st.session_state.get('_ap_last_loaded_id', '—')})"
                )

        st.divider()
        st.caption("Campos rellenados al buscar; puedes corregirlos antes de agendar.")
        fn = st.text_input("Nombre *", key="ap_fn")
        ln = st.text_input("Apellido *", key="ap_ln")
        birth_d = st.date_input("Fecha nacimiento *", key="ap_bd")
        email = st.text_input("Email *", key="ap_em")

        with st.expander("Contacto adicional / redes / emergencia", expanded=False):
            st.text_input("Dirección", key="ap_addr")
            st.text_input("Nacionalidad", key="ap_nat")
            st.text_input("Profesión", key="ap_prof")
            st.text_input("Email secundario", key="ap_se")
            st.text_area("Redes (JSON)", height=80, key="ap_sm")
            st.text_input("Contacto emergencia — nombre", key="ap_ecn")
            st.text_input("Contacto emergencia — teléfono", key="ap_ecp")

        st.checkbox("Es menor de edad", key="ap_minor")
        with st.expander("Tutor / representante (solo menores)", expanded=False):
            st.text_input("Nombre tutor", key="ap_gn")
            st.selectbox(
                "Tipo doc tutor",
                ["CC", "TI", "CE", "PAS"],
                key="ap_gdt",
                format_func=lambda x: {
                    "CC": "CC — Cédula",
                    "TI": "TI",
                    "CE": "CE",
                    "PAS": "PAS",
                }[x],
            )
            st.text_input("Documento tutor", key="ap_gdn")
            st.date_input("Fecha expedición doc tutor", key="ap_gdi")

        st.markdown("##### Cita")
        c1, c2 = st.columns(2)
        with c1:
            phone = st.text_input("Teléfono cita *", key="ap_phone")
            svc_options = list(configured_service_types())
            cur = st.session_state.get("ap_svc", svc_options[0] if svc_options else "tattoo")
            ix = 0
            if cur in svc_options:
                ix = svc_options.index(cur)
            service = st.selectbox("Tipo de servicio *", options=svc_options, index=ix, key="ap_svc")
        with c2:
            appointment_date = st.date_input("Fecha cita *", key="ap_ad", format="DD/MM/YYYY")
            date_str = appointment_date.strftime("%Y-%m-%d")
            detail = st.text_area("Detalle del trabajo", placeholder="Ej. manga…", height=80, key="ap_det")
            deposit = st.number_input("Depósito (COP) *", min_value=0.0, step=10000.0, key="ap_dep")
            st.caption(f"Valor: {_format_cop(deposit)}")

        full_name = f"{(fn or '').strip()} {(ln or '').strip()}".strip()

        if st.button("Crear cita", key="btn_appt_create"):
            if st.session_state.get("_appt_submitting"):
                st.warning("Solicitud en curso…")
            else:
                st.session_state["_appt_submitting"] = True
                try:
                    valid, errs = validate_appointment(full_name, phone.strip(), service, date_str, detail, deposit)
                    if not valid:
                        _show_validation_errors(errs)
                    elif not (st.session_state.get("ap_doc_n") or "").strip():
                        st.error("El número de documento del cliente es obligatorio.")
                    else:
                        doc_t = st.session_state.get("ap_doc_t", doc_type)
                        cust_payload: Dict[str, Any] = {
                            "first_name": (fn or "").strip(),
                            "last_name": (ln or "").strip(),
                            "birth_date": birth_d.isoformat(),
                            "document_type": doc_t,
                            "document_number": (st.session_state.get("ap_doc_n") or "").strip(),
                            "email": (email or "").strip(),
                            "phone_number": (phone or "").strip(),
                            "address": (st.session_state.get("ap_addr") or "").strip() or None,
                            "nationality": (st.session_state.get("ap_nat") or "").strip() or None,
                            "profession": (st.session_state.get("ap_prof") or "").strip() or None,
                            "secondary_email": (st.session_state.get("ap_se") or "").strip() or None,
                            "social_media": parse_social_media_json(st.session_state.get("ap_sm", "")),
                            "emergency_contact_name": (st.session_state.get("ap_ecn") or "").strip() or None,
                            "emergency_contact_phone": (st.session_state.get("ap_ecp") or "").strip() or None,
                            "is_minor": bool(st.session_state.get("ap_minor")),
                            "guardian_name": (st.session_state.get("ap_gn") or "").strip() or None,
                            "guardian_document_type": st.session_state.get("ap_gdt")
                            if st.session_state.get("ap_minor")
                            else None,
                            "guardian_document_number": (st.session_state.get("ap_gdn") or "").strip() or None,
                            "guardian_document_issue_date": (
                                st.session_state.get("ap_gdi").isoformat()
                                if st.session_state.get("ap_minor")
                                and st.session_state.get("ap_gdi")
                                else None
                            ),
                        }
                        with st.spinner("Validando y sincronizando cliente…"):
                            ok_c, msg_c, cid = sync_customer(
                                cust_payload, (st.session_state.get("ap_doc_n") or "").strip()
                            )
                        if not ok_c or cid is None:
                            st.error(msg_c)
                        else:
                            appt_payload = {
                                "name": full_name,
                                "phone": (phone or "").strip(),
                                "service": (service or "").strip(),
                                "date": date_str.strip(),
                                "detail": (detail or "").strip() or None,
                                "deposit": float(deposit),
                                "customer_id": cid,
                            }
                            ok_a, code_a, data_a = api_client.post_appointment(appt_payload)
                            if ok_a:
                                body = (
                                    json.dumps(data_a, ensure_ascii=False)
                                    if isinstance(data_a, dict)
                                    else str(data_a)
                                )
                                st.success(f"Cita creada: {body}")
                            else:
                                st.error(f"Error HTTP {code_a}: {_api_error(data_a)}")
                finally:
                    st.session_state["_appt_submitting"] = False

    with st.expander("Listado de citas", expanded=False):
        if st.button("Refrescar listado", key="btn_appt_list"):
            ok, code, data = api_client.get_appointments()
            if ok and isinstance(data, list):
                rows = []
                for appt in data:
                    rows.append(
                        {
                            "Nombre": appt.get("customer_name", appt.get("name", "")),
                            "Tipo de trabajo": appt.get("service_type", appt.get("service", "")),
                            "Depósito": _format_cop(appt.get("deposit", 0)),
                        }
                    )
                st.dataframe(rows, use_container_width=True, hide_index=True)
            else:
                st.markdown(
                    f'<div class="m-error">HTTP {code}: {_api_error(data)}</div>',
                    unsafe_allow_html=True,
                )
