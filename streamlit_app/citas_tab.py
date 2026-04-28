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


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _financial_row_values(row: dict[str, Any]) -> tuple[float, float, float]:
    """
    Normaliza montos para UI y resumen:
    - total nunca menor que abonado (fallback datos legacy)
    - pendiente: si viene `pending_balance` de la API/MySQL es la fuente de verdad
      (ej. tras anular con saldo ya puesto en 0 y crédito en otra columna);
      si no, pendiente = max(total − abonado − saldo a favor, 0) para no ignorar créditos.
    """
    abonado = max(_to_float(row.get("deposit"), 0.0), 0.0)
    total_raw = max(_to_float(row.get("total_amount"), 0.0), 0.0)
    total = max(total_raw, abonado)
    cred = max(_to_float(row.get("customer_credit"), 0.0), 0.0)
    raw_pb = row.get("pending_balance")
    if raw_pb is not None and raw_pb != "":
        pendiente = max(round(_to_float(raw_pb, 0.0), 2), 0.0)
    else:
        pendiente = max(round(total - abonado - cred, 2), 0.0)
    return total, abonado, pendiente


def _customer_credit_value(row: dict[str, Any]) -> float:
    """Saldo a favor del cliente asociado a esta cita (p. ej. traslado de abono al anular)."""
    return max(_to_float(row.get("customer_credit"), 0.0), 0.0)


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
        "ap_total": 0.0,
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
        "ap_total",
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
    total_amount = st.number_input("Valor total del trabajo (COP) *", min_value=0.0, step=10000.0, key="ap_total")
    deposit = st.number_input("Saldo abonado (COP) *", min_value=0.0, step=10000.0, key="ap_dep")
    pending_balance = round(float(total_amount) - float(deposit), 2)
    st.caption(f"Saldo pendiente calculado: {_format_cop(max(pending_balance, 0))}")

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
            if deposit > total_amount:
                st.error("El saldo abonado no puede ser mayor que el valor total del trabajo.")
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
                "total_amount": float(total_amount),
                "pending_balance": float(max(pending_balance, 0)),
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


def _status_pill_html(status: str) -> str:
    normalized = (status or "Agendada").strip().lower()
    cls = {
        "agendada": "pill-agendada",
        "reprogramada": "pill-reprogramada",
        "cancelada": "pill-cancelada",
        "finalizada": "pill-finalizada",
    }.get(normalized, "pill-default")
    return f'<span class="ap-pill {cls}">{status or "Agendada"}</span>'


def _render_cita_row_actions(r: Dict[str, Any]) -> None:
    """
    Agrupa Contrato + Mover junto al resto en un solo menú de acciones por fila
    (sustituye columnas dedicadas Contrato / Mover).
    """
    appt_id = int(r.get("id", 0) or 0)
    status = str(r.get("status") or "Agendada")
    has_customer = r.get("customer_id") is not None
    firmar_disabled = appt_id <= 0 or not has_customer or status in {"Cancelada", "Finalizada"}
    repro_disabled = appt_id <= 0 or status == "Cancelada"
    montos_disabled = appt_id <= 0 or status not in {"Agendada", "Reprogramada"}
    anular_disabled = appt_id <= 0 or status in {"Cancelada", "Finalizada"}

    pop = getattr(st, "popover", None)
    if pop:
        with pop("Acciones", use_container_width=True):
            if appt_id > 0:
                st.caption(f"Cita #{appt_id}")
            st.link_button(
                "Firmar contrato",
                url=f"?view=contract_sign&appointment_id={appt_id}",
                disabled=firmar_disabled,
                use_container_width=True,
                key=f"pop_firmar_{appt_id}",
            )
            if st.button(
                "Reprogramar cita",
                disabled=repro_disabled,
                use_container_width=True,
                key=f"pop_repr_{appt_id}",
                help="Antes columna «Mover»: cambiar fecha/detalle manteniendo el estado hábil.",
            ):
                st.session_state["_ap_reprogram_item"] = r
                st.rerun()
            if st.button(
                "Montos",
                disabled=montos_disabled,
                use_container_width=True,
                key=f"pop_fin_{appt_id}",
            ):
                st.session_state["_ap_fin_item"] = r
                st.rerun()
            if st.button(
                "Anular",
                disabled=anular_disabled,
                use_container_width=True,
                key=f"pop_can_{appt_id}",
            ):
                st.session_state["_ap_cancel_item"] = r
                st.rerun()
        return

    ln1, ln2 = st.columns(2)
    with ln1:
        st.link_button(
            "Firmar",
            url=f"?view=contract_sign&appointment_id={appt_id}",
            disabled=firmar_disabled,
            use_container_width=True,
            key=f"fb_compact_{appt_id}",
        )
    with ln2:
        if st.button("Mover", disabled=repro_disabled, use_container_width=True, key=f"fb_repr_{appt_id}"):
            st.session_state["_ap_reprogram_item"] = r
            st.rerun()
    bn1, bn2 = st.columns(2)
    with bn1:
        if st.button("Montos", disabled=montos_disabled, use_container_width=True, key=f"fb_fin_{appt_id}"):
            st.session_state["_ap_fin_item"] = r
            st.rerun()
    with bn2:
        if st.button("Anular", disabled=anular_disabled, use_container_width=True, key=f"fb_can_{appt_id}"):
            st.session_state["_ap_cancel_item"] = r
            st.rerun()


def _apply_appointment_filters(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    text = str(st.session_state.get("_ap_f_name") or "").strip().lower()
    svc = str(st.session_state.get("_ap_f_service") or "Todos")
    status = str(st.session_state.get("_ap_f_status") or "Todos")
    from_date = st.session_state.get("_ap_f_from")
    to_date = st.session_state.get("_ap_f_to")
    filtered: list[dict[str, Any]] = []
    for row in items:
        name_value = str(row.get("customer_name", row.get("name", "")) or "")
        service_value = str(row.get("service_type", row.get("service", "")) or "")
        status_value = str(row.get("status") or "Agendada")
        appt_date = _parse_date(row.get("appointment_date", row.get("date")))
        if text and text not in name_value.lower():
            continue
        if svc != "Todos" and service_value != svc:
            continue
        if status != "Todos" and status_value != status:
            continue
        if from_date and appt_date < from_date:
            continue
        if to_date and appt_date > to_date:
            continue
        filtered.append(row)
    return filtered


def _cleanup_reprogram_dialog_state() -> None:
    keys = ("_ap_reprogram_seed_appt_id", "ap_reprogram_date", "ap_reprogram_detail")
    for k in keys:
        st.session_state.pop(k, None)


@st.dialog("Reprogramar cita", width="medium", dismissible=False)
def _dialog_reprogramar_cita() -> None:
    appt = st.session_state.get("_ap_reprogram_item") or {}
    appt_id = int(appt.get("id", 0) or 0)
    if appt_id <= 0:
        st.error("No se encontró la cita a reprogramar.")
        if st.button("Cerrar", use_container_width=True):
            st.session_state.pop("_ap_reprogram_item", None)
            _cleanup_reprogram_dialog_state()
            st.rerun()
        return
    seed_key = "_ap_reprogram_seed_appt_id"
    current_date = _parse_date(appt.get("appointment_date", appt.get("date")))
    detail_default = str(appt.get("detail") or "")
    min_date_appt, max_date_appt = _date_range_100y_window()
    # Una sola fuente de verdad: session_state por key — evita value+key (provoca glitch del popover Calendar)
    if st.session_state.get(seed_key) != appt_id:
        st.session_state[seed_key] = appt_id
        st.session_state["ap_reprogram_date"] = current_date
        st.session_state["ap_reprogram_detail"] = detail_default

    st.caption(f"Cita #{appt_id} · {appt.get('customer_name', appt.get('name', ''))}")
    # Detalle primero para no autofocos en el calendar al abrir el diálogo
    new_detail = st.text_area(
        "Detalle actualizado (opcional)",
        height=90,
        key="ap_reprogram_detail",
    )
    new_date = st.date_input(
        "Nueva fecha de cita",
        min_value=min_date_appt,
        max_value=max_date_appt,
        key="ap_reprogram_date",
        format="DD/MM/YYYY",
    )
    c1, c2 = st.columns(2)
    with c1:
        if st.button(
            "Guardar reprogramación",
            type="primary",
            use_container_width=True,
            key="ap_reprogram_save_btn",
        ):
            ok, code, data = api_client.patch_appointment_reschedule(
                appt_id,
                new_date.strftime("%Y-%m-%d"),
                (new_detail or "").strip() or None,
            )
            if ok:
                st.success("Cita reprogramada correctamente.")
                st.session_state["_ap_reload"] = True
                st.session_state.pop("_ap_reprogram_item", None)
                _cleanup_reprogram_dialog_state()
                st.rerun()
            else:
                st.error(f"Error HTTP {code}: {_api_error(data)}")
    with c2:
        if st.button("Cancelar", use_container_width=True, key="ap_reprogram_close_btn"):
            st.session_state.pop("_ap_reprogram_item", None)
            _cleanup_reprogram_dialog_state()
            st.rerun()


def _label_cancel_abono(v: str) -> str:
    if v == "credito_cliente":
        return "Saldo a favor del cliente — el abono pasa a crédito interno y deja de contar como cobrado sobre la cita"
    return "Devolución — el abono deja la cita como no cobrado (sin saldo a favor aquí)"

@st.dialog("Confirmar anulación", width="medium", dismissible=False)
def _dialog_cancelar_cita() -> None:
    appt = st.session_state.get("_ap_cancel_item") or {}
    appt_id = int(appt.get("id", 0) or 0)
    if appt_id <= 0:
        st.error("No se encontró la cita a anular.")
        if st.button("Cerrar", use_container_width=True, key="ap_cancel_close_missing"):
            st.session_state.pop("_ap_cancel_item", None)
            st.rerun()
        return
    deposit = float(appt.get("deposit") or 0)
    warning = (
        f"Vas a anular la cita #{appt_id} de "
        f"{appt.get('customer_name', appt.get('name', 'cliente'))}. Esta acción cambia el estado a Cancelada."
    )
    if deposit > 0:
        warning += f" Hay {_format_cop(deposit)} abonados en esta fila."
    else:
        warning += " No hay abonos registrados en esta cita."
    st.warning(warning)

    cancel_abono: str
    if deposit > 0:
        st.markdown("Si hubo abono, cómo debe reflejarse para **resumen y totales**:", unsafe_allow_html=True)
        cancel_abono = st.radio(
            "Tratamiento del abono",
            ("credito_cliente", "devolucion"),
            format_func=_label_cancel_abono,
            horizontal=False,
            key=f"dlg_cancel_abono_radio_{appt_id}",
            label_visibility="visible",
        )
    else:
        cancel_abono = "devolucion"
        st.caption("Sin abono; la anulación solo cierra la cita en el sistema.")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Sí, anular", type="primary", use_container_width=True, key="ap_cancel_confirm_btn"):
            ok, code, data = api_client.patch_appointment_status(appt_id, "Cancelada", cancel_abono)
            if ok:
                st.session_state["_ap_reload"] = True
                st.session_state.pop("_ap_cancel_item", None)
                st.rerun()
            else:
                st.error(f"Error HTTP {code}: {_api_error(data)}")
    with c2:
        if st.button("No, volver", use_container_width=True, key="ap_cancel_back_btn"):
            st.session_state.pop("_ap_cancel_item", None)
            st.rerun()


@st.dialog("Ajustar montos", width="medium", dismissible=False)
def _dialog_ajustar_montos() -> None:
    appt = st.session_state.get("_ap_fin_item") or {}
    appt_id = int(appt.get("id", 0) or 0)
    status = str(appt.get("status") or "Agendada")
    if appt_id <= 0:
        st.error("No se encontró la cita.")
        if st.button("Cerrar", use_container_width=True, key="ap_fin_close_missing"):
            st.session_state.pop("_ap_fin_item", None)
            st.rerun()
        return
    if status not in {"Agendada", "Reprogramada"}:
        st.error("Solo puedes editar montos en estados Agendada o Reprogramada.")
        if st.button("Cerrar", use_container_width=True, key="ap_fin_close_invalid"):
            st.session_state.pop("_ap_fin_item", None)
            st.rerun()
        return
    st.caption(f"Cita #{appt_id} · Estado: {status}")
    current_total = float(appt.get("total_amount") or 0)
    current_deposit = float(appt.get("deposit") or 0)
    total_amount = st.number_input(
        "Valor total del trabajo (COP)",
        min_value=0.0,
        step=10000.0,
        value=current_total,
        key="ap_fin_total",
    )
    pending = round(float(total_amount) - float(current_deposit), 2)
    st.caption(f"Abonado actual: {_format_cop(current_deposit)}")
    st.caption(f"Saldo pendiente calculado: {_format_cop(max(pending, 0))}")

    ok_p, code_p, payments = api_client.get_appointment_payments(appt_id)
    st.markdown("##### Historial de abonos")
    if ok_p and isinstance(payments, list):
        if payments:
            for p in payments:
                when = str(p.get("created_at") or "")
                note = str(p.get("note") or "Sin nota")
                amount = _to_float(p.get("amount"), 0.0)
                st.write(f"- {when[:19]} · {_format_cop(amount)} · {note}")
        else:
            st.info("Aún no hay abonos registrados.")
    else:
        st.warning(f"No se pudo cargar historial (HTTP {code_p}).")

    extra_payment = st.number_input(
        "Agregar abono adicional (COP)",
        min_value=0.0,
        step=10000.0,
        value=0.0,
        key="ap_fin_extra_payment",
    )
    payment_note = st.text_input(
        "Nota del abono (opcional)",
        value="",
        key="ap_fin_extra_note",
        placeholder="Ej: abono en efectivo",
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Guardar", type="primary", use_container_width=True, key="ap_fin_save_btn"):
            if current_deposit > total_amount:
                st.error("El abonado acumulado no puede ser mayor al valor total.")
                return
            ok, code, data = api_client.patch_appointment_financials(
                appt_id,
                float(total_amount),
                float(current_deposit),
                float(max(pending, 0)),
            )
            if not ok:
                st.error(f"Error HTTP {code}: {_api_error(data)}")
                return
            if extra_payment > 0:
                ok_pay, code_pay, data_pay = api_client.post_appointment_payment(
                    appt_id,
                    float(extra_payment),
                    (payment_note or "").strip() or None,
                )
                if not ok_pay:
                    st.error(f"No se pudo registrar abono (HTTP {code_pay}): {_api_error(data_pay)}")
                    return
            st.success("Montos y abonos actualizados.")
            st.session_state["_ap_reload"] = True
            st.session_state.pop("_ap_fin_item", None)
            st.rerun()
    with c2:
        if st.button("Cancelar", use_container_width=True, key="ap_fin_cancel_btn"):
            st.session_state.pop("_ap_fin_item", None)
            st.session_state.pop("ap_fin_total", None)
            st.session_state.pop("ap_fin_extra_payment", None)
            st.session_state.pop("ap_fin_extra_note", None)
            st.rerun()


def render_citas_tab() -> None:
    if "_ap_page" not in st.session_state:
        st.session_state["_ap_page"] = 0
    if "_ap_limit" not in st.session_state:
        st.session_state["_ap_limit"] = 10
    if "_ap_reload" not in st.session_state:
        st.session_state["_ap_reload"] = True
    if "_ap_f_name" not in st.session_state:
        st.session_state["_ap_f_name"] = ""
    if "_ap_f_service" not in st.session_state:
        st.session_state["_ap_f_service"] = "Todos"
    if "_ap_f_status" not in st.session_state:
        st.session_state["_ap_f_status"] = "Todos"
    if "_ap_f_from" not in st.session_state:
        st.session_state["_ap_f_from"] = None
    if "_ap_f_to" not in st.session_state:
        st.session_state["_ap_f_to"] = None

    st.subheader("Agendamiento de citas")
    st.markdown(
        """
        <style>
        .ap-pill {
            display: inline-block;
            border-radius: 999px;
            padding: 0.18rem 0.62rem;
            font-size: 0.78rem;
            font-weight: 600;
            line-height: 1.1rem;
            border: 1px solid transparent;
        }
        .pill-agendada { background: #e8f1ff; color: #16406f; border-color: #bdd2f4; }
        .pill-reprogramada { background: #fff2df; color: #7a4a03; border-color: #f5d3a0; }
        .pill-cancelada { background: #fdeaea; color: #7f1f1f; border-color: #efbcbc; }
        .pill-finalizada { background: #e8f8ec; color: #1f6b31; border-color: #b8e2c2; }
        .pill-default { background: #f2f3f5; color: #374151; border-color: #d1d5db; }
        .ap-col-title {
            display: inline-block;
            font-weight: 700;
            letter-spacing: 0.02em;
            color: #111827;
            background: #f3f4f6;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 0.18rem 0.45rem;
            white-space: nowrap;
            line-height: 1.35;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
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
    svc_values = sorted(
        {
            str(i.get("service_type", i.get("service", "")) or "").strip()
            for i in items
            if str(i.get("service_type", i.get("service", "")) or "").strip()
        }
    )
    status_values = ["Agendada", "Reprogramada", "Finalizada", "Cancelada"]
    f1, f2, f3, f4, f5 = st.columns([1.3, 1.0, 1.0, 0.9, 0.9])
    with f1:
        st.text_input("Filtrar nombre", key="_ap_f_name", placeholder="Nombre cliente")
    with f2:
        st.selectbox("Servicio", options=["Todos", *svc_values], key="_ap_f_service")
    with f3:
        st.selectbox("Estado", options=["Todos", *status_values], key="_ap_f_status")
    with f4:
        # Solo `key`; no mezclar value=session_state[misma_clave]: evita comportamiento raro del calendario
        st.date_input("Desde", key="_ap_f_from")
    with f5:
        st.date_input("Hasta", key="_ap_f_to")

    filtered_items = _apply_appointment_filters(items)
    total_trabajo = 0.0
    total_abonado = 0.0
    total_pendiente = 0.0
    total_credito_favor = 0.0
    for row in filtered_items:
        row_total, row_abonado, row_pendiente = _financial_row_values(row)
        total_trabajo += row_total
        total_abonado += row_abonado
        total_pendiente += row_pendiente
        total_credito_favor += _customer_credit_value(row)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total trabajo", _format_cop(total_trabajo))
    m2.metric("Total abonado", _format_cop(total_abonado))
    m3.metric("Total saldo pendiente", _format_cop(total_pendiente))
    m4.metric("Saldo a favor (filtro)", _format_cop(total_credito_favor))

    st.caption(
        "**Saldo pendiente** (filas y totales): si la API trae **pendiente** calculado guardado "
        "(p. ej. tras anular), ese valor cuenta; si no, se usa **total − abonado − a favor**. "
        "Así el resumen sí resta el saldo a favor del cliente cuando toca calcular desde cero."
    )

    total = len(filtered_items)
    limit = int(st.session_state["_ap_limit"])
    page = int(st.session_state["_ap_page"])
    total_pages = max(1, (total + limit - 1) // limit)
    if page >= total_pages:
        page = max(0, total_pages - 1)
        st.session_state["_ap_page"] = page
    start = page * limit
    rows = filtered_items[start : start + limit]

    st.caption(
        "**Contrato** (firma) y **Reprogramar cita** (antes columna «Mover») quedaron unificados en **Acciones**."
    )
    # Índices: Nombre … Abonado(4) Pendiente(5): un poco más ancha para «Pendiente» en una línea
    colw = [1.48, 0.92, 0.82, 0.78, 0.78, 0.92, 0.85, 0.76, 1.52]
    h1, h2, h3, h4, h5, h6, h7, h8, h9 = st.columns(colw)
    h1.markdown('<span class="ap-col-title">Nombre</span>', unsafe_allow_html=True)
    h2.markdown('<span class="ap-col-title">Servicio</span>', unsafe_allow_html=True)
    h3.markdown('<span class="ap-col-title">Fecha</span>', unsafe_allow_html=True)
    h4.markdown('<span class="ap-col-title">Total</span>', unsafe_allow_html=True)
    h5.markdown('<span class="ap-col-title">Abonado</span>', unsafe_allow_html=True)
    h6.markdown('<span class="ap-col-title">Pendiente</span>', unsafe_allow_html=True)
    h7.markdown('<span class="ap-col-title">A favor</span>', unsafe_allow_html=True)
    h8.markdown('<span class="ap-col-title">Estado</span>', unsafe_allow_html=True)
    h9.markdown('<span class="ap-col-title">Acciones</span>', unsafe_allow_html=True)
    for r in rows:
        c1, c2, c3, c4, c5, c6, c7, c8, c9 = st.columns(colw)
        c1.write(r.get("customer_name", r.get("name", "")))
        c2.write(r.get("service_type", r.get("service", "")))
        c3.write(str(r.get("appointment_date", r.get("date", ""))))
        total_amount, deposit_amount, pending_balance = _financial_row_values(r)
        credito = _customer_credit_value(r)
        c4.write(_format_cop(total_amount))
        c5.write(_format_cop(deposit_amount))
        c6.write(_format_cop(pending_balance))
        c7.write("—" if credito <= 0 else _format_cop(credito))
        status = str(r.get("status") or "Agendada")
        c8.markdown(_status_pill_html(status), unsafe_allow_html=True)
        with c9:
            _render_cita_row_actions(r)

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
        st.caption(f"Página {page + 1}/{total_pages} · Total filtrado: {total} cita(s)")

    if st.session_state.get("_ap_dlg") == "create":
        _dialog_agendar_cita()
    if st.session_state.get("_ap_reprogram_item"):
        _dialog_reprogramar_cita()
    if st.session_state.get("_ap_fin_item"):
        _dialog_ajustar_montos()
    if st.session_state.get("_ap_cancel_item"):
        _dialog_cancelar_cita()
