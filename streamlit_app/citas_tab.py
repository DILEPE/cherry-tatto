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


def _is_minor_by_birth_date(birth_date: date) -> bool:
    today = date.today()
    years = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    return years < 18


def _shift_years(base: date, years: int) -> date:
    target_year = base.year + years
    try:
        return base.replace(year=target_year)
    except ValueError:
        return base.replace(year=target_year, day=28)


def _date_range_100y_past() -> tuple[date, date]:
    today = date.today()
    return _shift_years(today, -100), today


def _date_range_100y_window() -> tuple[date, date]:
    today = date.today()
    return _shift_years(today, -100), _shift_years(today, 100)


def _validate_document_rules(
    *,
    birth_date: date,
    document_type: str,
    has_document_issue_date: bool,
    document_issue_date: date,
) -> Optional[str]:
    today = date.today()
    if not has_document_issue_date:
        return None
    if document_issue_date > today:
        return "La fecha de expedición del documento no puede ser futura."
    if document_type == "TI":
        if not _is_minor_by_birth_date(birth_date):
            return "Si el documento es TI, la fecha de nacimiento debe indicar menor de 18 años."
        return None
    adulthood_date = _shift_years(birth_date, 18)
    if document_issue_date < adulthood_date:
        return "Para documentos distintos de TI, la expedición debe ser al menos 18 años después del nacimiento."
    return None


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
    ddi = row.get("document_issue_date")
    st.session_state["ap_has_ddi"] = bool(ddi)
    st.session_state["ap_ddi"] = _parse_date(ddi) if ddi else date(2015, 1, 1)
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
    st.session_state["ap_has_gdi"] = bool(gdiv)
    st.session_state["ap_gdi"] = _parse_date(gdiv) if gdiv else date(2000, 1, 1)
    st.session_state["ap_phone"] = (row.get("phone_number") or "").strip()
    st.session_state["_ap_last_loaded_id"] = row.get("id")
    st.session_state["_ap_prefill_meta"] = (
        f"{st.session_state['ap_fn']} {st.session_state['ap_ln']}".strip()
    )
    st.session_state["_ap_doc_verified"] = True
    st.session_state["_ap_doc_verified_doc"] = st.session_state["ap_doc_n"]


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
    st.session_state["ap_has_gdi"] = False
    st.session_state["ap_gdi"] = date(2000, 1, 1)
    st.session_state["ap_phone"] = ""
    st.session_state["ap_doc_t"] = "CC"
    st.session_state["ap_doc_n"] = doc_keep
    st.session_state["ap_has_ddi"] = False
    st.session_state["ap_ddi"] = date(2015, 1, 1)
    st.session_state["_ap_prefill_meta"] = None
    st.session_state["_ap_last_loaded_id"] = None
    st.session_state["_ap_doc_verified"] = False
    st.session_state["_ap_doc_verified_doc"] = ""


def _init_appt_form_state_once() -> None:
    """Valores iniciales solo la primera vez (hasta `st.rerun` típico)."""
    if st.session_state.get("_ap_form_ready"):
        return
    defaults: Dict[str, Any] = {
        "ap_doc_t": "CC",
        "ap_doc_n": "",
        "ap_has_ddi": False,
        "ap_ddi": date(2015, 1, 1),
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
        "ap_has_gdi": False,
        "ap_gdi": date(2000, 1, 1),
        "ap_phone": "",
        "ap_ad": date.today(),
        "ap_det": "",
        "ap_dep": 0.0,
        "_ap_doc_verified": False,
        "_ap_doc_verified_doc": "",
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
        st.session_state["_ap_doc_verified"] = True
        st.session_state["_ap_doc_verified_doc"] = str(pending["doc"]).strip()
        st.session_state["_ap_flash"] = (
            "warning",
            "No hay cliente con ese documento. Completa los datos; se creará al guardar la cita.",
        )


def _reset_appointment_form_state() -> None:
    keys = (
        "ap_doc_t",
        "ap_doc_n",
        "ap_has_ddi",
        "ap_ddi",
        "ap_fn",
        "ap_ln",
        "ap_bd",
        "ap_em",
        "ap_addr",
        "ap_nat",
        "ap_prof",
        "ap_se",
        "ap_sm",
        "ap_ecn",
        "ap_ecp",
        "ap_minor",
        "ap_gn",
        "ap_gdt",
        "ap_gdn",
        "ap_has_gdi",
        "ap_gdi",
        "ap_phone",
        "ap_ad",
        "ap_det",
        "ap_dep",
        "_ap_doc_verified",
        "_ap_doc_verified_doc",
        "_ap_last_loaded_id",
        "_ap_prefill_meta",
    )
    for key in keys:
        st.session_state.pop(key, None)
    st.session_state.pop("_ap_pending_lookup", None)
    st.session_state.pop("_ap_flash", None)
    st.session_state["_ap_form_ready"] = False


@st.dialog("Agendar cita", width="large", dismissible=False)
def _dialog_agendar_cita() -> None:
    _init_appt_form_state_once()
    _process_pending_lookup()
    min_date_100, max_date_today = _date_range_100y_past()
    min_date_appt, max_date_appt = _date_range_100y_window()

    st.markdown("##### Verificación de cliente por cédula")
    d1, d2 = st.columns([2, 1])
    with d1:
        st.selectbox("Tipo documento *", ["CC", "TI", "CE", "PAS"], key="ap_doc_t")
        st.text_input("Número documento *", key="ap_doc_n", placeholder="Sin espacios")
        current_doc = (st.session_state.get("ap_doc_n") or "").strip()
        verified_doc = (st.session_state.get("_ap_doc_verified_doc") or "").strip()
        if current_doc and verified_doc and current_doc != verified_doc:
            st.session_state["_ap_doc_verified"] = False
            st.session_state["_ap_doc_verified_doc"] = ""
    with d2:
        st.write("")
        if st.button("Verificar cédula", type="primary", key="ap_doc_lookup"):
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

    verified = bool(st.session_state.get("_ap_doc_verified")) and (
        (st.session_state.get("_ap_doc_verified_doc") or "").strip()
        == (st.session_state.get("ap_doc_n") or "").strip()
    )
    if not verified:
        st.info("Primero confirma/verifica el número de documento para habilitar el formulario de cita.")
        if st.button("Cerrar", use_container_width=True, key="btn_appt_close_unverified"):
            _reset_appointment_form_state()
            st.session_state.pop("_ap_dlg", None)
            st.rerun()
        return

    fn = st.text_input("Nombre *", key="ap_fn")
    ln = st.text_input("Apellido *", key="ap_ln")
    birth_d = st.date_input(
        "Fecha nacimiento *",
        key="ap_bd",
        min_value=min_date_100,
        max_value=max_date_today,
    )
    email = st.text_input("Email *", key="ap_em")
    st.checkbox("Registrar fecha expedición documento cliente", key="ap_has_ddi")
    st.date_input(
        "Fecha expedición documento cliente",
        key="ap_ddi",
        min_value=min_date_100,
        max_value=max_date_today,
    )
    st.checkbox("Es menor de edad", key="ap_minor")

    if st.session_state.get("ap_minor"):
        with st.expander("Tutor / representante (obligatorio para menores)", expanded=True):
            st.text_input("Nombre del tutor *", key="ap_gn")
            st.selectbox("Tipo de documento del tutor *", ["CC", "TI", "CE", "PAS"], key="ap_gdt")
            st.text_input("Número de documento del tutor *", key="ap_gdn")
            st.checkbox("Registrar fecha expedición documento tutor", key="ap_has_gdi")
            st.date_input(
                "Fecha expedición documento tutor",
                key="ap_gdi",
                min_value=min_date_100,
                max_value=max_date_today,
            )

    phone = st.text_input("Teléfono cita *", key="ap_phone")
    svc_options = list(configured_service_types())
    cur = st.session_state.get("ap_svc", svc_options[0] if svc_options else "tattoo")
    ix = svc_options.index(cur) if cur in svc_options else 0
    service = st.selectbox("Tipo de servicio *", options=svc_options, index=ix, key="ap_svc")
    appointment_date = st.date_input(
        "Fecha cita *",
        key="ap_ad",
        min_value=min_date_appt,
        max_value=max_date_appt,
        format="DD/MM/YYYY",
    )
    detail = st.text_area("Detalle del trabajo", height=80, key="ap_det")
    deposit = st.number_input("Depósito (COP) *", min_value=0.0, step=10000.0, key="ap_dep")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Crear cita", type="primary", use_container_width=True, key="btn_appt_create"):
            doc = (st.session_state.get("ap_doc_n") or "").strip()
            verified = bool(st.session_state.get("_ap_doc_verified")) and st.session_state.get(
                "_ap_doc_verified_doc"
            ) == doc
            if not verified:
                st.error("Debes verificar la cédula antes de agendar la cita.")
                return

            expected_minor = _is_minor_by_birth_date(birth_d)
            if bool(st.session_state.get("ap_minor")) != expected_minor:
                st.error("El check de menor de edad no coincide con la fecha de nacimiento.")
                return
            doc_error = _validate_document_rules(
                birth_date=birth_d,
                document_type=str(st.session_state.get("ap_doc_t") or "CC"),
                has_document_issue_date=bool(st.session_state.get("ap_has_ddi")),
                document_issue_date=st.session_state.get("ap_ddi"),
            )
            if doc_error:
                st.error(doc_error)
                return

            if st.session_state.get("ap_minor"):
                if not (st.session_state.get("ap_gn") or "").strip() or not (
                    st.session_state.get("ap_gdn") or ""
                ).strip() or not st.session_state.get("ap_has_gdi"):
                    st.error("Para menores, los datos del tutor son obligatorios.")
                    return
                if st.session_state.get("ap_gdt") == "TI":
                    st.error("El tipo de documento del tutor no puede ser TI.")
                    return
                gdi = st.session_state.get("ap_gdi")
                today = date.today()
                tutor_years_since_issue = today.year - gdi.year - ((today.month, today.day) < (gdi.month, gdi.day))
                if tutor_years_since_issue < 18:
                    st.error("La fecha de expedición del documento del tutor debe tener al menos 18 años respecto a hoy.")
                    return

            full_name = f"{(fn or '').strip()} {(ln or '').strip()}".strip()
            date_str = appointment_date.strftime("%Y-%m-%d")
            valid, errs = validate_appointment(full_name, (phone or "").strip(), service, date_str, detail, deposit)
            if not valid:
                _show_validation_errors(errs)
                return

            cust_payload: Dict[str, Any] = {
                "first_name": (fn or "").strip(),
                "last_name": (ln or "").strip(),
                "birth_date": birth_d.isoformat(),
                "document_type": st.session_state.get("ap_doc_t"),
                "document_number": doc,
                "document_issue_date": st.session_state.get("ap_ddi").isoformat()
                if st.session_state.get("ap_has_ddi")
                else None,
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
                "guardian_document_issue_date": st.session_state.get("ap_gdi").isoformat()
                if st.session_state.get("ap_minor") and st.session_state.get("ap_has_gdi")
                else None,
            }
            ok_c, msg_c, cid = sync_customer(cust_payload, doc)
            if not ok_c or cid is None:
                st.error(msg_c)
                return
            appt_payload = {
                "name": full_name,
                "phone": (phone or "").strip(),
                "service": (service or "").strip(),
                "date": date_str,
                "detail": (detail or "").strip() or None,
                "deposit": float(deposit),
                "customer_id": cid,
            }
            ok_a, code_a, data_a = api_client.post_appointment(appt_payload)
            if ok_a:
                st.session_state["_ap_reload"] = True
                st.success("Cita creada correctamente.")
                _reset_appointment_form_state()
                st.session_state.pop("_ap_dlg", None)
                st.rerun()
            else:
                st.error(f"Error HTTP {code_a}: {_api_error(data_a)}")
    with c2:
        if st.button("Cancelar", use_container_width=True, key="btn_appt_cancel"):
            _reset_appointment_form_state()
            st.session_state.pop("_ap_dlg", None)
            st.rerun()


def _fetch_appointments() -> None:
    ok, code, data = api_client.get_appointments()
    if ok and isinstance(data, list):
        st.session_state["_ap_list"] = data
        st.session_state["_ap_err"] = None
    else:
        st.session_state["_ap_list"] = []
        st.session_state["_ap_err"] = f"HTTP {code}: {_api_error(data)}"


def render_citas_tab() -> None:
    if "_ap_page" not in st.session_state:
        st.session_state["_ap_page"] = 0
    if "_ap_limit" not in st.session_state:
        st.session_state["_ap_limit"] = 10
    if "_ap_reload" not in st.session_state:
        st.session_state["_ap_reload"] = True

    st.subheader("Agendamiento de citas")
    b1, b2 = st.columns([1, 1])
    with b1:
        if st.button("➕ Agendar cita", type="primary", use_container_width=True):
            st.session_state["_ap_dlg"] = "create"
    with b2:
        if st.button("Actualizar listado", use_container_width=True):
            st.session_state["_ap_reload"] = True

    if st.session_state.get("_ap_reload"):
        _fetch_appointments()
        st.session_state["_ap_reload"] = False

    if st.session_state.get("_ap_err"):
        st.error(st.session_state["_ap_err"])

    items = list(st.session_state.get("_ap_list") or [])
    total = len(items)
    limit = int(st.session_state["_ap_limit"])
    page = int(st.session_state["_ap_page"])
    start = page * limit
    rows = items[start : start + limit]

    h1, h2, h3, h4, h5 = st.columns([2.0, 1.3, 1.0, 1.0, 1.0])
    h1.markdown("**Nombre**")
    h2.markdown("**Servicio**")
    h3.markdown("**Fecha**")
    h4.markdown("**Depósito**")
    h5.markdown("**Contrato**")
    for r in rows:
        c1, c2, c3, c4, c5 = st.columns([2.0, 1.3, 1.0, 1.0, 1.0])
        c1.write(r.get("customer_name", r.get("name", "")))
        c2.write(r.get("service_type", r.get("service", "")))
        c3.write(str(r.get("appointment_date", r.get("date", ""))))
        c4.write(_format_cop(r.get("deposit", 0)))
        with c5:
            appt_id = int(r.get("id", 0) or 0)
            has_customer = r.get("customer_id") is not None
            st.link_button(
                "Firmar",
                url=f"?view=contract_sign&appointment_id={appt_id}",
                disabled=(appt_id <= 0 or not has_customer),
                use_container_width=True,
            )

    p1, p2, p3 = st.columns([1, 1, 2.5])
    with p1:
        st.write("")
        if st.button("◀", disabled=page <= 0, use_container_width=True):
            st.session_state["_ap_page"] = max(0, page - 1)
            st.rerun()
    with p2:
        st.write("")
        if st.button("▶", disabled=(page + 1) * limit >= total if total else True, use_container_width=True):
            st.session_state["_ap_page"] = page + 1
            st.rerun()
    with p3:
        st.write("")
        total_pages = max(1, (total + limit - 1) // limit)
        st.caption(f"Página {page + 1}/{total_pages} · Total: {total} cita(s)")

    if st.session_state.get("_ap_dlg") == "create":
        _dialog_agendar_cita()
