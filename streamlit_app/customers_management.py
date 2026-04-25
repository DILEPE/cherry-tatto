"""Streamlit: pestaña Gestión de clientes (español, diálogos nativos, acciones por fila)."""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import streamlit as st

from streamlit_app import api_client
from streamlit_app.customer_sync import parse_social_media_json


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


def _detail(payload: Any) -> str:
    if isinstance(payload, dict):
        return str(payload.get("detail", payload))
    return str(payload)


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


def _close_dialogs() -> None:
    for k in (
        "_cust_dlg",
        "_cust_dlg_id",
        "_cust_dlg_del_name",
        "_cust_dlg_del_confirm",
    ):
        st.session_state.pop(k, None)


@st.dialog("Registrar cliente", width="large")
def _dialog_crear_cliente() -> None:
    st.markdown("##### Datos personales")
    a, b = st.columns(2)
    with a:
        c_fn = st.text_input("Nombre *", key="dlg_cc_fn")
        c_ln = st.text_input("Apellido *", key="dlg_cc_ln")
        c_bd = st.date_input("Fecha de nacimiento *", value=date(1990, 1, 1), key="dlg_cc_bd")
        c_dt = st.selectbox(
            "Tipo de documento *",
            ["CC", "TI", "CE", "PAS"],
            format_func=lambda x: {"CC": "CC — Cédula", "TI": "TI — Tarjeta identidad", "CE": "CE — Extranjería", "PAS": "PAS — Pasaporte"}[x],
            key="dlg_cc_dt",
        )
        c_dn = st.text_input("Número de documento *", key="dlg_cc_dn")
    with b:
        c_em = st.text_input("Correo electrónico *", key="dlg_cc_em")
        c_ph = st.text_input("Teléfono *", key="dlg_cc_ph")
        c_nat = st.text_input("Nacionalidad", key="dlg_cc_nat")
        c_prof = st.text_input("Profesión", key="dlg_cc_prof")

    with st.expander("Contacto y redes", expanded=False):
        c_addr = st.text_input("Dirección", key="dlg_cc_addr")
        c_se = st.text_input("Correo secundario", key="dlg_cc_se")
        c_sm = st.text_area("Redes sociales (JSON)", height=70, key="dlg_cc_sm")

    with st.expander("Contacto de emergencia", expanded=False):
        ecn = st.text_input("Nombre contacto emergencia", key="dlg_cc_ecn")
        ecp = st.text_input("Teléfono contacto emergencia", key="dlg_cc_ecp")

    c_minor = st.checkbox("Es menor de edad", key="dlg_cc_minor")
    with st.expander("Datos del tutor o representante", expanded=False):
        gn = st.text_input("Nombre del tutor", key="dlg_cc_gn")
        gdt = st.selectbox(
            "Tipo documento tutor",
            ["CC", "TI", "CE", "PAS"],
            format_func=lambda x: {"CC": "CC — Cédula", "TI": "TI — Tarjeta identidad", "CE": "CE — Extranjería", "PAS": "PAS — Pasaporte"}[x],
            key="dlg_cc_gdt",
        )
        gdn = st.text_input("Número documento tutor", key="dlg_cc_gdn")
        gdi = st.date_input("Fecha expedición documento tutor", value=date(2000, 1, 1), key="dlg_cc_gdi")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Registrar cliente", type="primary", use_container_width=True, key="dlg_cc_submit"):
            payload: Dict[str, Any] = {
                "first_name": c_fn.strip(),
                "last_name": c_ln.strip(),
                "birth_date": c_bd.isoformat(),
                "document_type": c_dt,
                "document_number": c_dn.strip(),
                "email": c_em.strip(),
                "phone_number": c_ph.strip(),
                "address": c_addr.strip() or None,
                "nationality": c_nat.strip() or None,
                "profession": c_prof.strip() or None,
                "secondary_email": c_se.strip() or None,
                "social_media": parse_social_media_json(c_sm),
                "emergency_contact_name": ecn.strip() or None,
                "emergency_contact_phone": ecp.strip() or None,
                "is_minor": bool(c_minor),
                "guardian_name": gn.strip() or None,
                "guardian_document_type": gdt if c_minor else None,
                "guardian_document_number": gdn.strip() or None,
                "guardian_document_issue_date": gdi.isoformat() if c_minor else None,
            }
            ok, code, data = api_client.post_customer(payload)
            if ok:
                st.success("Cliente registrado correctamente.")
                st.session_state["_cust_reload"] = True
                _close_dialogs()
                st.rerun()
            else:
                st.error(f"No se pudo registrar (HTTP {code}): {_detail(data)}")
    with c2:
        if st.button("Cancelar", use_container_width=True, key="dlg_cc_cancel"):
            _close_dialogs()
            st.rerun()


@st.dialog("Detalle del cliente", width="large")
def _dialog_ver_cliente(cliente_id: int) -> None:
    ok, code, data = api_client.get_customer(cliente_id)
    if not ok or not isinstance(data, dict):
        st.error(f"No se pudo cargar (HTTP {code}): {_detail(data)}")
    else:
        st.markdown(f"**ID:** {data.get('id')}")
        st.markdown(
            f"**Nombre:** {data.get('first_name', '')} {data.get('last_name', '')}  \n"
            f"**Documento:** {data.get('document_type')} {data.get('document_number')}  \n"
            f"**Correo:** {data.get('email')}  \n"
            f"**Teléfono:** {data.get('phone_number')}"
        )
        with st.expander("Más datos", expanded=False):
            st.json(data)
    if st.button("Cerrar", use_container_width=True, key="dlg_view_close"):
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

    st.markdown("##### Datos personales")
    a, b = st.columns(2)
    with a:
        ef = st.text_input("Nombre *", value=ed.get("first_name", ""), key="dlg_ed_fn")
        el = st.text_input("Apellido *", value=ed.get("last_name", ""), key="dlg_ed_ln")
        eb = st.date_input("Fecha de nacimiento *", value=_parse_date(ed.get("birth_date")), key="dlg_ed_bd")
        edt = st.selectbox(
            "Tipo de documento *",
            ["CC", "TI", "CE", "PAS"],
            index=_doc_type_index(ed.get("document_type")),
            format_func=lambda x: {"CC": "CC — Cédula", "TI": "TI — Tarjeta identidad", "CE": "CE — Extranjería", "PAS": "PAS — Pasaporte"}[x],
            key="dlg_ed_dt",
        )
        edn = st.text_input("Número de documento *", value=ed.get("document_number", ""), key="dlg_ed_dn")
    with b:
        eem = st.text_input("Correo *", value=ed.get("email", ""), key="dlg_ed_em")
        eph = st.text_input("Teléfono *", value=ed.get("phone_number", ""), key="dlg_ed_ph")
        enat = st.text_input("Nacionalidad", value=ed.get("nationality") or "", key="dlg_ed_nat")
        eprof = st.text_input("Profesión", value=ed.get("profession") or "", key="dlg_ed_prof")

    with st.expander("Contacto y redes", expanded=False):
        eaddr = st.text_input("Dirección", value=ed.get("address") or "", key="dlg_ed_addr")
        ese = st.text_input("Correo secundario", value=ed.get("secondary_email") or "", key="dlg_ed_se")
        esm = st.text_area(
            "Redes sociales (JSON)",
            value=json.dumps(ed.get("social_media") or {}, ensure_ascii=False) if ed.get("social_media") else "",
            key="dlg_ed_sm",
        )

    with st.expander("Emergencia y tutor", expanded=False):
        een = st.text_input("Nombre contacto emergencia", value=ed.get("emergency_contact_name") or "", key="dlg_ed_ecn")
        eep = st.text_input("Teléfono contacto emergencia", value=ed.get("emergency_contact_phone") or "", key="dlg_ed_ecp")
        emin = st.checkbox("Es menor de edad", value=bool(ed.get("is_minor")), key="dlg_ed_minor")
        egn = st.text_input("Nombre del tutor", value=ed.get("guardian_name") or "", key="dlg_ed_gn")
        egdt = st.selectbox(
            "Tipo documento tutor",
            ["CC", "TI", "CE", "PAS"],
            index=_doc_type_index(ed.get("guardian_document_type")),
            format_func=lambda x: {"CC": "CC — Cédula", "TI": "TI — Tarjeta identidad", "CE": "CE — Extranjería", "PAS": "PAS — Pasaporte"}[x],
            key="dlg_ed_gdt",
        )
        egdn = st.text_input("Número documento tutor", value=ed.get("guardian_document_number") or "", key="dlg_ed_gdn")
        egdi_raw = ed.get("guardian_document_issue_date")
        egdi = st.date_input(
            "Fecha expedición documento tutor",
            value=_parse_date(egdi_raw) if egdi_raw else date(2000, 1, 1),
            key="dlg_ed_gdi",
        )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Guardar cambios", type="primary", use_container_width=True, key="dlg_ed_save"):
            payload = {
                "first_name": ef.strip(),
                "last_name": el.strip(),
                "birth_date": eb.isoformat(),
                "document_type": edt,
                "document_number": edn.strip(),
                "email": eem.strip(),
                "phone_number": eph.strip(),
                "address": eaddr.strip() or None,
                "nationality": enat.strip() or None,
                "profession": eprof.strip() or None,
                "secondary_email": ese.strip() or None,
                "social_media": parse_social_media_json(esm),
                "emergency_contact_name": een.strip() or None,
                "emergency_contact_phone": eep.strip() or None,
                "is_minor": bool(emin),
                "guardian_name": egn.strip() or None,
                "guardian_document_type": egdt if emin else None,
                "guardian_document_number": egdn.strip() or None,
                "guardian_document_issue_date": egdi.isoformat() if emin else None,
            }
            ok, code, data = api_client.put_customer(cliente_id, payload)
            if ok:
                st.success("Cliente actualizado.")
                st.session_state.pop("_dlg_edit_payload", None)
                st.session_state.pop("_dlg_edit_id", None)
                st.session_state["_cust_reload"] = True
                _close_dialogs()
                st.rerun()
            else:
                st.error(f"HTTP {code}: {_detail(data)}")
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
                st.success("Cliente eliminado.")
                st.session_state["_cust_reload"] = True
                _close_dialogs()
                st.rerun()
            else:
                st.error(f"HTTP {code}: {_detail(data)}")
    with c2:
        if st.button("No, cancelar", use_container_width=True, key="dlg_del_no"):
            _close_dialogs()
            st.rerun()


def render_customers_management_tab() -> None:
    st.subheader("Gestión de clientes")
    st.caption("Alta, consulta, edición y baja lógica. Usa los botones de cada fila.")

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
        _fetch_list(search, limit, page)
        st.session_state["_cust_reload"] = False

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

    # Cabecera de tabla manual
    h1, h2, h3, h4, h5, h6, h7 = st.columns([1.8, 1.2, 1.6, 1.0, 0.55, 0.55, 0.55])
    with h1:
        st.markdown("**Nombre**")
    with h2:
        st.markdown("**Documento**")
    with h3:
        st.markdown("**Correo**")
    with h4:
        st.markdown("**Teléfono**")
    with h5:
        st.markdown("**Ver**")
    with h6:
        st.markdown("**Editar**")
    with h7:
        st.markdown("**Eliminar**")

    for it in items:
        cid = int(it["id"])
        nombre = f"{it.get('first_name', '')} {it.get('last_name', '')}".strip()
        doc = f"{it.get('document_type', '')} {it.get('document_number', '')}".strip()
        c1, c2, c3, c4, c5, c6, c7 = st.columns([1.8, 1.2, 1.6, 1.0, 0.55, 0.55, 0.55])
        with c1:
            st.write(nombre)
        with c2:
            st.write(doc)
        with c3:
            st.write(it.get("email", ""))
        with c4:
            st.write(it.get("phone_number", ""))
        with c5:
            if st.button("Ver", key=f"cust_v_{cid}", use_container_width=True):
                st.session_state["_cust_dlg"] = "view"
                st.session_state["_cust_dlg_id"] = cid
        with c6:
            if st.button("Editar", key=f"cust_e_{cid}", use_container_width=True):
                st.session_state["_cust_dlg"] = "edit"
                st.session_state["_cust_dlg_id"] = cid
                st.session_state.pop("_dlg_edit_payload", None)
                st.session_state.pop("_dlg_edit_id", None)
        with c7:
            if st.button("Eliminar", key=f"cust_d_{cid}", use_container_width=True):
                st.session_state["_cust_dlg"] = "delete"
                st.session_state["_cust_dlg_id"] = cid
                st.session_state["_cust_dlg_del_name"] = nombre

    st.divider()

    # Paginación al pie
    p1, p2, p3, p4, p5 = st.columns([1, 1, 1.2, 1, 1])
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
    with p3:
        new_limit = st.selectbox(
            "Registros por página",
            options=[10, 20, 50, 100],
            index=[10, 20, 50, 100].index(limit) if limit in (10, 20, 50, 100) else 1,
            key="cust_limit_sel",
        )
        if new_limit != limit:
            st.session_state["_cust_limit"] = new_limit
            st.session_state["_cust_page"] = 0
            st.session_state["_cust_reload"] = True
            st.rerun()
    with p4:
        st.metric("Página actual", page + 1)
    with p5:
        st.metric("Total registros", total)

    # Diálogos (invocación nativa Streamlit)
    dlg = st.session_state.get("_cust_dlg")
    dlg_id = st.session_state.get("_cust_dlg_id")

    if dlg == "create":
        _dialog_crear_cliente()
    elif dlg == "view" and dlg_id:
        _dialog_ver_cliente(int(dlg_id))
    elif dlg == "edit" and dlg_id:
        _dialog_editar_cliente(int(dlg_id))
    elif dlg == "delete" and dlg_id:
        _dialog_eliminar_cliente(int(dlg_id), st.session_state.get("_cust_dlg_del_name", ""))
