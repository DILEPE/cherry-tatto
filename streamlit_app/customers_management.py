"""Streamlit: pestaña Gestión de clientes (español, diálogos nativos, acciones por fila)."""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import streamlit as st

from app.schemas.customer import CUSTOMER_BIRTH_PENDING, SOCIAL_MEDIA_MAX_LEN
from streamlit_app import api_client
from streamlit_app.customer_sync import social_media_api_to_form_text, social_media_form_text_to_api
from streamlit_app.validation import (
    mobile_phone_co_10_error,
    optional_mobile_phone_co_10_error,
    social_media_text_error,
)


def _parse_date(val: Any) -> date:
    if isinstance(val, date):
        return val
    if isinstance(val, str) and val:
        return datetime.strptime(val[:10], "%Y-%m-%d").date()
    return date(1990, 1, 1)


def _doc_type_index(val: Any) -> int:
    opts = ["CC", "TI", "CE", "PAS"]
    v = val if val in opts else "CC"
    return opts.index(v)


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


def _date_range_100y() -> tuple[date, date]:
    today = date.today()
    return _shift_years(today, -100), today


def _clamp_date(value: date, min_value: date, max_value: date) -> date:
    if value < min_value:
        return min_value
    if value > max_value:
        return max_value
    return value


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
            return "Si el tipo de documento es TI, la fecha de nacimiento debe indicar menor de 18 años."
        return None
    adulthood_date = _shift_years(birth_date, 18)
    if document_issue_date < adulthood_date:
        return "Para documentos distintos de TI, la expedición debe ser al menos 18 años después del nacimiento."
    return None


def _detail(payload: Any) -> str:
    if isinstance(payload, dict):
        return str(payload.get("detail", payload))
    return str(payload)


_CUST_ACTION_INFO_KEY = "_cust_action_info"


def _queue_cust_action_success(msg: str) -> None:
    """Confirmación visible en el siguiente rerun de la pestaña (tras cerrar el diálogo)."""
    st.session_state[_CUST_ACTION_INFO_KEY] = msg


def _render_cust_action_feedback() -> None:
    msg = st.session_state.pop(_CUST_ACTION_INFO_KEY, None)
    if msg:
        st.toast(msg, icon="✅", duration="long")


def _fetch_list(search: str, limit: int, page: int) -> None:
    offset = page * limit
    params: Dict[str, Any] = {"limit": limit, "offset": offset}
    if search.strip():
        params["search"] = search.strip()
    ok, code, data = api_client.get_customers(**params)
    if ok and isinstance(data, dict):
        st.session_state["_cust_list"] = data
        st.session_state["_cust_last_error"] = None
    else:
        st.session_state["_cust_list"] = None
        st.session_state["_cust_last_error"] = (code, _detail(data))


def _render_customer_row_actions(cid: int, nombre: str) -> None:
    """Menú único por fila (mismo patrón que Gestión citas): popover o botones compactos."""

    def _dispatch_edit() -> None:
        st.session_state["_cust_dlg"] = "edit"
        st.session_state["_cust_dlg_id"] = cid
        st.session_state.pop("_dlg_edit_payload", None)
        st.session_state.pop("_dlg_edit_id", None)

    def _dispatch_delete() -> None:
        st.session_state["_cust_dlg"] = "delete"
        st.session_state["_cust_dlg_id"] = cid
        st.session_state["_cust_dlg_del_name"] = nombre

    def _dispatch_contracts() -> None:
        st.session_state["_cust_dlg"] = "contracts"
        st.session_state["_cust_dlg_id"] = cid
        st.session_state["_cust_dlg_contract_name"] = nombre

    pop = getattr(st, "popover", None)
    if pop:
        with pop("Acciones", use_container_width=True):
            if cid > 0:
                st.caption(f"Cliente #{cid}")
            if nombre:
                st.caption(nombre[:80] + ("…" if len(nombre) > 80 else ""))
            if st.button("Editar", key=f"cust_e_{cid}", use_container_width=True):
                _dispatch_edit()
            if st.button("Eliminar", key=f"cust_d_{cid}", use_container_width=True):
                _dispatch_delete()
            if st.button("Contratos", key=f"cust_ct_{cid}", use_container_width=True):
                _dispatch_contracts()
        return

    ln1, ln2 = st.columns(2)
    with ln1:
        if st.button("Editar", key=f"cust_fb_e_{cid}", use_container_width=True):
            _dispatch_edit()
    with ln2:
        if st.button("Eliminar", key=f"cust_fb_d_{cid}", use_container_width=True):
            _dispatch_delete()
    bn1, bn2 = st.columns(2)
    with bn1:
        if st.button("Contratos", key=f"cust_fb_ct_{cid}", use_container_width=True):
            _dispatch_contracts()


def _close_dialogs() -> None:
    for k in (
        "_cust_dlg",
        "_cust_dlg_id",
        "_cust_dlg_del_name",
        "_cust_dlg_del_confirm",
        "_cust_dlg_contract_name",
    ):
        st.session_state.pop(k, None)


def _reset_create_customer_form_state() -> None:
    keys = (
        "dlg_cc_fn",
        "dlg_cc_ln",
        "dlg_cc_bd",
        "dlg_cc_dt",
        "dlg_cc_dn",
        "dlg_cc_has_ddi",
        "dlg_cc_ddi",
        "dlg_cc_em",
        "dlg_cc_ph",
        "dlg_cc_nat",
        "dlg_cc_prof",
        "dlg_cc_addr",
        "dlg_cc_sm",
        "dlg_cc_ecn",
        "dlg_cc_ecp",
        "dlg_cc_minor",
        "dlg_cc_gn",
        "dlg_cc_gdt",
        "dlg_cc_gdn",
        "dlg_cc_has_gdi",
        "dlg_cc_gdi",
    )
    for key in keys:
        st.session_state.pop(key, None)


@st.dialog("Registrar cliente", width="large", dismissible=False)
def _dialog_crear_cliente() -> None:
    min_date_100, max_date_today = _date_range_100y()
    st.markdown("##### Datos personales")
    a, b = st.columns(2)
    with a:
        c_fn = st.text_input("Nombre *", key="dlg_cc_fn")
        c_ln = st.text_input("Apellido *", key="dlg_cc_ln")
        c_bd = st.date_input(
            "Fecha de nacimiento *",
            value=date(1990, 1, 1),
            min_value=min_date_100,
            max_value=max_date_today,
            key="dlg_cc_bd",
        )
        c_dt = st.selectbox(
            "Tipo de documento *",
            ["CC", "TI", "CE", "PAS"],
            format_func=lambda x: {"CC": "CC — Cédula", "TI": "TI — Tarjeta identidad", "CE": "CE — Extranjería", "PAS": "PAS — Pasaporte"}[x],
            key="dlg_cc_dt",
        )
        c_dn = st.text_input("Número de documento *", key="dlg_cc_dn")
        c_has_ddi = st.checkbox("Registrar fecha de expedición del documento del cliente", key="dlg_cc_has_ddi")
        c_ddi = st.date_input(
            "Fecha de expedición del documento del cliente",
            value=date(2015, 1, 1),
            min_value=min_date_100,
            max_value=max_date_today,
            key="dlg_cc_ddi",
        )
    with b:
        c_em = st.text_input("Correo electrónico *", key="dlg_cc_em")
        c_ph = st.text_input(
            "Celular *",
            key="dlg_cc_ph",
            help="10 dígitos (solo se cuentan los números).",
        )
        c_nat = st.text_input("Nacionalidad (recomendado)", key="dlg_cc_nat")
        c_prof = st.text_input("Profesión (recomendado)", key="dlg_cc_prof")

    with st.expander("Contacto y redes", expanded=False):
        c_addr = st.text_input("Dirección", key="dlg_cc_addr")
        c_sm = st.text_area(
            "Redes sociales (recomendado)",
            height=70,
            key="dlg_cc_sm",
            max_chars=SOCIAL_MEDIA_MAX_LEN,
            help=f"Texto plano, máximo {SOCIAL_MEDIA_MAX_LEN} caracteres. No uses JSON.",
        )

    with st.expander("Contacto de emergencia", expanded=False):
        ecn = st.text_input("Nombre contacto emergencia", key="dlg_cc_ecn")
        ecp = st.text_input(
            "Celular contacto emergencia",
            key="dlg_cc_ecp",
            help="Si lo completas: 10 dígitos.",
        )

    c_minor = st.checkbox("Es menor de edad", key="dlg_cc_minor")
    if c_minor:
        st.info("Menor de edad: debes completar los datos del tutor.")
    with st.expander("Datos del tutor o representante (menores de edad)", expanded=c_minor):
        gn = st.text_input("Nombre del tutor o representante", key="dlg_cc_gn")
        gdt = st.selectbox(
            "Tipo de documento del tutor",
            ["CC", "TI", "CE", "PAS"],
            format_func=lambda x: {"CC": "CC — Cédula", "TI": "TI — Tarjeta identidad", "CE": "CE — Extranjería", "PAS": "PAS — Pasaporte"}[x],
            key="dlg_cc_gdt",
        )
        gdn = st.text_input("Número de documento del tutor", key="dlg_cc_gdn")
        g_has_gdi = st.checkbox(
            "Registrar fecha de expedición del documento del tutor",
            key="dlg_cc_has_gdi",
        )
        gdi = st.date_input(
            "Fecha de expedición del documento del tutor",
            value=date(2000, 1, 1),
            min_value=min_date_100,
            max_value=max_date_today,
            key="dlg_cc_gdi",
        )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Registrar cliente", type="primary", use_container_width=True, key="dlg_cc_submit"):
            expected_minor = _is_minor_by_birth_date(c_bd)
            if bool(c_minor) != expected_minor:
                st.error("El check de menor de edad no coincide con la fecha de nacimiento.")
                return
            doc_error = _validate_document_rules(
                birth_date=c_bd,
                document_type=c_dt,
                has_document_issue_date=bool(c_has_ddi),
                document_issue_date=c_ddi,
            )
            if doc_error:
                st.error(doc_error)
                return
            if c_minor:
                if not gn.strip() or not gdn.strip() or not g_has_gdi:
                    st.error("Para menores: nombre tutor, documento tutor y fecha de expedición son obligatorios.")
                    return
                if gdt == "TI":
                    st.error("El tipo de documento del tutor no puede ser TI.")
                    return
                today = date.today()
                tutor_years_since_issue = today.year - gdi.year - ((today.month, today.day) < (gdi.month, gdi.day))
                if tutor_years_since_issue < 18:
                    st.error("La fecha de expedición del documento del tutor debe tener al menos 18 años respecto a hoy.")
                    return

            ph_err = mobile_phone_co_10_error(c_ph.strip())
            if ph_err:
                st.error(ph_err)
                return
            ecp_err = optional_mobile_phone_co_10_error(ecp.strip())
            if ecp_err:
                st.error(f"Contacto de emergencia: {ecp_err}")
                return
            sm_err = social_media_text_error(str(c_sm or ""))
            if sm_err:
                st.error(sm_err)
                return
            sm_parsed = social_media_form_text_to_api(str(c_sm or ""))
            soft_missing: List[str] = []
            if not c_nat.strip():
                soft_missing.append("nacionalidad")
            if not c_prof.strip():
                soft_missing.append("profesión")
            if not sm_parsed:
                soft_missing.append("redes sociales")
            if soft_missing:
                st.warning(
                    "**Recomendado completar:** "
                    + ", ".join(soft_missing)
                    + ". Puedes registrar el cliente igualmente."
                )

            payload: Dict[str, Any] = {
                "first_name": c_fn.strip(),
                "last_name": c_ln.strip(),
                "birth_date": c_bd.isoformat(),
                "document_type": c_dt,
                "document_number": c_dn.strip(),
                "document_issue_date": c_ddi.isoformat() if c_has_ddi else None,
                "email": c_em.strip(),
                "phone_number": c_ph.strip(),
                "address": c_addr.strip() or None,
                "nationality": c_nat.strip() or None,
                "profession": c_prof.strip() or None,
                "social_media": sm_parsed,
                "emergency_contact_name": ecn.strip() or None,
                "emergency_contact_phone": ecp.strip() or None,
                "is_minor": bool(c_minor),
                "guardian_name": gn.strip() or None,
                "guardian_document_type": gdt if c_minor else None,
                "guardian_document_number": gdn.strip() or None,
                "guardian_document_issue_date": gdi.isoformat() if c_minor and g_has_gdi else None,
            }
            ok, code, data = api_client.post_customer(payload)
            if ok:
                _queue_cust_action_success("Cliente registrado correctamente.")
                st.session_state["_cust_reload"] = True
                _reset_create_customer_form_state()
                _close_dialogs()
                st.rerun()
            else:
                st.toast(
                    f"No se pudo registrar (HTTP {code}): {_detail(data)}",
                    icon="❌",
                    duration="long",
                )
    with c2:
        if st.button("Cancelar", use_container_width=True, key="dlg_cc_cancel"):
            _reset_create_customer_form_state()
            _close_dialogs()
            st.rerun()


@st.dialog("Editar cliente", width="large")
def _dialog_editar_cliente(cliente_id: int) -> None:
    if "_dlg_edit_payload" not in st.session_state or st.session_state.get("_dlg_edit_id") != cliente_id:
        ok, code, data = api_client.get_customer(cliente_id)
        if not ok or not isinstance(data, dict):
            st.error(f"No se pudo cargar (HTTP {code}): {_detail(data)}")
            if st.button("Cerrar", key="dlg_ed_err_close"):
                _close_dialogs()
                st.session_state.pop("_dlg_edit_payload", None)
                st.session_state.pop("_dlg_edit_id", None)
                st.rerun()
            return
        st.session_state["_dlg_edit_payload"] = data
        st.session_state["_dlg_edit_id"] = cliente_id

    ed = st.session_state["_dlg_edit_payload"]

    if _parse_date(ed.get("birth_date")) == CUSTOMER_BIRTH_PENDING:
        st.info(
            "Este cliente tiene fecha de nacimiento **provisional** (creado solo al agendar). "
            "Indica la fecha real para que las reglas de documento y menor de edad funcionen bien."
        )

    min_date_100, max_date_today = _date_range_100y()
    st.markdown("##### Datos personales")
    a, b = st.columns(2)
    with a:
        ef = st.text_input("Nombre *", value=ed.get("first_name", ""), key="dlg_ed_fn")
        el = st.text_input("Apellido *", value=ed.get("last_name", ""), key="dlg_ed_ln")
        eb = st.date_input(
            "Fecha de nacimiento *",
            value=_clamp_date(_parse_date(ed.get("birth_date")), min_date_100, max_date_today),
            min_value=min_date_100,
            max_value=max_date_today,
            key="dlg_ed_bd",
        )
        edt = st.selectbox(
            "Tipo de documento *",
            ["CC", "TI", "CE", "PAS"],
            index=_doc_type_index(ed.get("document_type")),
            format_func=lambda x: {"CC": "CC — Cédula", "TI": "TI — Tarjeta identidad", "CE": "CE — Extranjería", "PAS": "PAS — Pasaporte"}[x],
            key="dlg_ed_dt",
        )
        edn = st.text_input("Número de documento *", value=ed.get("document_number", ""), key="dlg_ed_dn")
        eddi_raw = ed.get("document_issue_date")
        ehas_ddi = st.checkbox(
            "Registrar fecha de expedición del documento del cliente",
            value=bool(eddi_raw),
            key="dlg_ed_has_ddi",
        )
        eddi = st.date_input(
            "Fecha de expedición del documento del cliente",
            value=_clamp_date(_parse_date(eddi_raw), min_date_100, max_date_today)
            if eddi_raw
            else date(2015, 1, 1),
            min_value=min_date_100,
            max_value=max_date_today,
            key="dlg_ed_ddi",
        )
    with b:
        eem = st.text_input("Correo *", value=ed.get("email", ""), key="dlg_ed_em")
        eph = st.text_input(
            "Celular *",
            value=ed.get("phone_number", ""),
            key="dlg_ed_ph",
            help="10 dígitos (solo se cuentan los números).",
        )
        enat = st.text_input("Nacionalidad (recomendado)", value=ed.get("nationality") or "", key="dlg_ed_nat")
        eprof = st.text_input("Profesión (recomendado)", value=ed.get("profession") or "", key="dlg_ed_prof")

    with st.expander("Contacto y redes", expanded=False):
        eaddr = st.text_input("Dirección", value=ed.get("address") or "", key="dlg_ed_addr")
        esm = st.text_area(
            "Redes sociales (recomendado)",
            value=social_media_api_to_form_text(ed.get("social_media")),
            key="dlg_ed_sm",
            max_chars=SOCIAL_MEDIA_MAX_LEN,
            help=f"Texto plano, máximo {SOCIAL_MEDIA_MAX_LEN} caracteres. No uses JSON.",
        )

    with st.expander("Emergencia y tutor", expanded=False):
        een = st.text_input("Nombre contacto emergencia", value=ed.get("emergency_contact_name") or "", key="dlg_ed_ecn")
        eep = st.text_input(
            "Celular contacto emergencia",
            value=ed.get("emergency_contact_phone") or "",
            key="dlg_ed_ecp",
            help="Si lo completas: 10 dígitos.",
        )
        emin = st.checkbox("Es menor de edad", value=bool(ed.get("is_minor")), key="dlg_ed_minor")
        if emin:
            st.info("Menor de edad: debes completar los datos del tutor.")
        egn = st.text_input("Nombre del tutor", value=ed.get("guardian_name") or "", key="dlg_ed_gn")
        egdt = st.selectbox(
            "Tipo de documento del tutor",
            ["CC", "TI", "CE", "PAS"],
            index=_doc_type_index(ed.get("guardian_document_type")),
            format_func=lambda x: {"CC": "CC — Cédula", "TI": "TI — Tarjeta identidad", "CE": "CE — Extranjería", "PAS": "PAS — Pasaporte"}[x],
            key="dlg_ed_gdt",
        )
        egdn = st.text_input("Número de documento del tutor", value=ed.get("guardian_document_number") or "", key="dlg_ed_gdn")
        egdi_raw = ed.get("guardian_document_issue_date")
        ehas_gdi = st.checkbox(
            "Registrar fecha de expedición del documento del tutor",
            value=bool(egdi_raw),
            key="dlg_ed_has_gdi",
        )
        egdi = st.date_input(
            "Fecha de expedición del documento del tutor",
            value=_clamp_date(_parse_date(egdi_raw), min_date_100, max_date_today)
            if egdi_raw
            else date(2000, 1, 1),
            min_value=min_date_100,
            max_value=max_date_today,
            key="dlg_ed_gdi",
        )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Guardar cambios", type="primary", use_container_width=True, key="dlg_ed_save"):
            expected_minor = _is_minor_by_birth_date(eb)
            if bool(emin) != expected_minor:
                st.error("El check de menor de edad no coincide con la fecha de nacimiento.")
                return
            doc_error = _validate_document_rules(
                birth_date=eb,
                document_type=edt,
                has_document_issue_date=bool(ehas_ddi),
                document_issue_date=eddi,
            )
            if doc_error:
                st.error(doc_error)
                return
            if emin:
                if not egn.strip() or not egdn.strip() or not ehas_gdi:
                    st.error("Para menores: nombre tutor, documento tutor y fecha de expedición son obligatorios.")
                    return
                if egdt == "TI":
                    st.error("El tipo de documento del tutor no puede ser TI.")
                    return
                today = date.today()
                tutor_years_since_issue = today.year - egdi.year - ((today.month, today.day) < (egdi.month, egdi.day))
                if tutor_years_since_issue < 18:
                    st.error("La fecha de expedición del documento del tutor debe tener al menos 18 años respecto a hoy.")
                    return

            ph_err = mobile_phone_co_10_error(eph.strip())
            if ph_err:
                st.error(ph_err)
                return
            eep_err = optional_mobile_phone_co_10_error(eep.strip())
            if eep_err:
                st.error(f"Contacto de emergencia: {eep_err}")
                return
            sm_err = social_media_text_error(str(esm or ""))
            if sm_err:
                st.error(sm_err)
                return
            sm_parsed_ed = social_media_form_text_to_api(str(esm or ""))
            soft_missing_ed: List[str] = []
            if not enat.strip():
                soft_missing_ed.append("nacionalidad")
            if not eprof.strip():
                soft_missing_ed.append("profesión")
            if not sm_parsed_ed:
                soft_missing_ed.append("redes sociales")
            if soft_missing_ed:
                st.warning(
                    "**Recomendado completar:** "
                    + ", ".join(soft_missing_ed)
                    + ". Puedes guardar igualmente."
                )

            payload = {
                "first_name": ef.strip(),
                "last_name": el.strip(),
                "birth_date": eb.isoformat(),
                "document_type": edt,
                "document_number": edn.strip(),
                "document_issue_date": eddi.isoformat() if ehas_ddi else None,
                "email": eem.strip(),
                "phone_number": eph.strip(),
                "address": eaddr.strip() or None,
                "nationality": enat.strip() or None,
                "profession": eprof.strip() or None,
                "social_media": sm_parsed_ed,
                "emergency_contact_name": een.strip() or None,
                "emergency_contact_phone": eep.strip() or None,
                "is_minor": bool(emin),
                "guardian_name": egn.strip() or None,
                "guardian_document_type": egdt if emin else None,
                "guardian_document_number": egdn.strip() or None,
                "guardian_document_issue_date": egdi.isoformat() if emin and ehas_gdi else None,
            }
            ok, code, data = api_client.put_customer(cliente_id, payload)
            if ok:
                _queue_cust_action_success("Cliente actualizado.")
                st.session_state.pop("_dlg_edit_payload", None)
                st.session_state.pop("_dlg_edit_id", None)
                st.session_state["_cust_reload"] = True
                _close_dialogs()
                st.rerun()
            else:
                st.toast(
                    f"HTTP {code}: {_detail(data)}",
                    icon="❌",
                    duration="long",
                )
    with c2:
        if st.button("Cancelar", use_container_width=True, key="dlg_ed_cancel"):
            st.session_state.pop("_dlg_edit_payload", None)
            st.session_state.pop("_dlg_edit_id", None)
            _close_dialogs()
            st.rerun()


@st.dialog("Eliminar cliente", width="medium")
def _dialog_eliminar_cliente(cliente_id: int, nombre: str) -> None:
    st.warning(f"¿Eliminar de forma lógica al cliente **{nombre}** (ID {cliente_id})?")
    st.caption("El registro quedará marcado como eliminado (soft delete).")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Sí, eliminar", type="primary", use_container_width=True, key="dlg_del_yes"):
            ok, code, data = api_client.delete_customer(cliente_id)
            if ok:
                _queue_cust_action_success("Cliente eliminado.")
                st.session_state["_cust_reload"] = True
                _close_dialogs()
                st.rerun()
            else:
                st.toast(
                    f"HTTP {code}: {_detail(data)}",
                    icon="❌",
                    duration="long",
                )
    with c2:
        if st.button("No, cancelar", use_container_width=True, key="dlg_del_no"):
            _close_dialogs()
            st.rerun()


@st.dialog("Contratos firmados del cliente", width="large", dismissible=False)
def _dialog_contracts_cliente(cliente_id: int, nombre: str) -> None:
    st.markdown(f"**Cliente:** {nombre} (ID {cliente_id})")
    ok, code, data = api_client.get_customer_contracts(cliente_id)
    if not ok or not isinstance(data, list):
        st.error(f"No se pudo cargar contratos (HTTP {code}): {_detail(data)}")
    elif not data:
        st.info("Este cliente no tiene contratos firmados.")
    else:
        h1, h2, h3, h4, h5 = st.columns([0.9, 1.0, 1.3, 1.3, 1.0])
        h1.markdown("**ID**")
        h2.markdown("**Cita**")
        h3.markdown("**Servicio**")
        h4.markdown("**Fecha cita**")
        h5.markdown("**Ver**")
        for row in data:
            c1, c2, c3, c4, c5 = st.columns([0.9, 1.0, 1.3, 1.3, 1.0])
            c1.write(row.get("id"))
            c2.write(row.get("appointment_id"))
            c3.write(row.get("service_type", ""))
            c4.write(str(row.get("appointment_date", "")))
            with c5:
                cid = int(row.get("id", 0) or 0)
                st.link_button(
                    "Contenido",
                    url=f"?view=contract_read&contract_id={cid}",
                    use_container_width=True,
                    disabled=cid <= 0,
                )
    if st.button("Cerrar", use_container_width=True, key="dlg_contracts_close"):
        _close_dialogs()
        st.rerun()


def render_customers_management_tab() -> None:
    st.subheader("Gestión de clientes")

    if "_cust_page" not in st.session_state:
        st.session_state["_cust_page"] = 0
    if "_cust_limit" not in st.session_state:
        st.session_state["_cust_limit"] = 20
    if "_cust_search_q" not in st.session_state:
        st.session_state["_cust_search_q"] = ""
    if "_cust_reload" not in st.session_state:
        st.session_state["_cust_reload"] = True

    # Barra superior: búsqueda + crear
    r1, r2, r3, r4 = st.columns([2.2, 1, 0.8, 0.8])
    with r1:
        st.text_input(
            "Buscar por nombre, documento o correo",
            key="cust_q_input",
            placeholder="Ej. Pérez, 1234567890…",
        )
    with r2:
        st.write("")
        st.write("")
        if st.button("Buscar", use_container_width=True, key="cust_btn_search"):
            st.session_state["_cust_search_q"] = st.session_state.get("cust_q_input", "").strip()
            st.session_state["_cust_page"] = 0
            st.session_state["_cust_reload"] = True
    with r3:
        st.write("")
        st.write("")
        if st.button("Actualizar", use_container_width=True, key="cust_btn_refresh"):
            st.session_state["_cust_search_q"] = st.session_state.get("cust_q_input", "").strip()
            st.session_state["_cust_reload"] = True
    with r4:
        st.write("")
        st.write("")
        if st.button("➕ Crear", use_container_width=True, type="primary", key="cust_btn_create"):
            st.session_state["_cust_dlg"] = "create"

    search = st.session_state.get("_cust_search_q", "")
    limit = int(st.session_state["_cust_limit"])
    page = int(st.session_state["_cust_page"])

    if st.session_state.get("_cust_reload"):
        with st.spinner("Cargando clientes…"):
            _fetch_list(search, limit, page)
        st.session_state["_cust_reload"] = False

    _render_cust_action_feedback()

    err = st.session_state.get("_cust_last_error")
    if err:
        st.error(f"Error al cargar listado (HTTP {err[0]}): {err[1]}")

    lst = st.session_state.get("_cust_list")
    items: List[Dict[str, Any]] = []
    total = 0
    if lst and isinstance(lst, dict):
        total = int(lst.get("total", 0))
        items = list(lst.get("items") or [])

    st.markdown(f"**{total}** cliente(s) en total · mostrando página **{page + 1}** de **{max(1, (total + limit - 1) // limit)}**")

    st.markdown(
            """
            <style>
              .cust-col-title {
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

    cust_colw = [1.62, 1.22, 1.52, 1.12, 1.52]
    h1, h2, h3, h4, h5 = st.columns(cust_colw)
    h1.markdown('<span class="cust-col-title">Nombre</span>', unsafe_allow_html=True)
    h2.markdown('<span class="cust-col-title">Documento</span>', unsafe_allow_html=True)
    h3.markdown('<span class="cust-col-title">Correo</span>', unsafe_allow_html=True)
    h4.markdown('<span class="cust-col-title">Teléfono</span>', unsafe_allow_html=True)
    h5.markdown('<span class="cust-col-title">Acciones</span>', unsafe_allow_html=True)

    for it in items:
        cid = int(it["id"])
        nombre = f"{it.get('first_name', '')} {it.get('last_name', '')}".strip()
        doc = f"{it.get('document_type', '')} {it.get('document_number', '')}".strip()
        c1, c2, c3, c4, c5 = st.columns(cust_colw)
        with c1:
            st.write(nombre)
        with c2:
            st.write(doc)
        with c3:
            st.write(it.get("email", ""))
        with c4:
            st.write(it.get("phone_number", ""))
        with c5:
            _render_customer_row_actions(cid, nombre)

    st.divider()

    # Paginación al pie: botones, selector y resumen en una sola línea visual alineada
    total_pages = max(1, (total + limit - 1) // limit)
    picked_limit = limit

    p1, p2, p_tail = st.columns([1, 1, 5])
    with p1:
        if st.button("◀ Anterior", disabled=page <= 0, use_container_width=True, key="cust_prev"):
            st.session_state["_cust_page"] = max(0, page - 1)
            st.session_state["_cust_reload"] = True
            st.rerun()
    with p2:
        if st.button("Siguiente ▶", disabled=(page + 1) * limit >= total if total else True, use_container_width=True, key="cust_next"):
            st.session_state["_cust_page"] = page + 1
            st.session_state["_cust_reload"] = True
            st.rerun()

    with p_tail:
        t_sel, t_info = st.columns([2.2, 2.8])
        with t_sel:
            lab_col, dd_col = st.columns([1.25, 1])
            with lab_col:
                st.markdown(
                    '<div style="display:flex;align-items:center;min-height:2.75rem;font-size:0.875rem;">Por página</div>',
                    unsafe_allow_html=True,
                )
            with dd_col:
                picked_limit = st.selectbox(
                    "_cust_rp",
                    options=[10, 20, 50, 100],
                    index=[10, 20, 50, 100].index(limit) if limit in (10, 20, 50, 100) else 1,
                    key="cust_limit_sel",
                    label_visibility="collapsed",
                    help="Cuántos registros mostrar por página.",
                )
        with t_info:
            st.markdown(
                f'<div style="display:flex;align-items:center;min-height:2.75rem;font-size:0.875rem;opacity:0.85;">'
                f"Página {page + 1}/{total_pages} · Total: {total}</div>",
                unsafe_allow_html=True,
            )

    if picked_limit != limit:
        st.session_state["_cust_limit"] = picked_limit
        st.session_state["_cust_page"] = 0
        st.session_state["_cust_reload"] = True
        st.rerun()

    # Diálogos (invocación nativa Streamlit)
    dlg = st.session_state.get("_cust_dlg")
    dlg_id = st.session_state.get("_cust_dlg_id")

    if dlg == "create":
        _dialog_crear_cliente()
    elif dlg == "edit" and dlg_id:
        _dialog_editar_cliente(int(dlg_id))
    elif dlg == "delete" and dlg_id:
        _dialog_eliminar_cliente(int(dlg_id), st.session_state.get("_cust_dlg_del_name", ""))
    elif dlg == "contracts" and dlg_id:
        _dialog_contracts_cliente(int(dlg_id), st.session_state.get("_cust_dlg_contract_name", ""))
