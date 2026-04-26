"""Streamlit: administrador de contratos (plantillas/versiones + texto final con datos cliente)."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

import streamlit as st
import streamlit.components.v1 as components

from streamlit_app import api_client


def _detail(payload: Any) -> str:
    if isinstance(payload, dict):
        return str(payload.get("detail", payload))
    return str(payload)


def _close_dialogs() -> None:
    for k in ("_ctadm_dlg", "_ctadm_dlg_id"):
        st.session_state.pop(k, None)


def _load_templates(*, only_active: bool) -> None:
    ok, code, data = api_client.get_templates(only_active=only_active)
    if ok and isinstance(data, list):
        st.session_state["_ctadm_templates"] = data
        st.session_state["_ctadm_error"] = None
    else:
        st.session_state["_ctadm_templates"] = []
        st.session_state["_ctadm_error"] = f"HTTP {code}: {_detail(data)}"


def _fetch_customer_by_document(document_number: str) -> tuple[bool, str, Optional[dict[str, Any]]]:
    doc = (document_number or "").strip()
    if len(doc) < 3:
        return False, "Ingresa un documento válido (mín. 3 caracteres).", None
    ok, code, data = api_client.get_customers(limit=1, offset=0, document_number=doc)
    if not ok:
        return False, f"HTTP {code}: {_detail(data)}", None
    items = (data or {}).get("items") or []
    if not items:
        return False, "No se encontró cliente con ese documento.", None
    return True, "ok", items[0]


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
    rendered = template_content
    for key, value in replacements.items():
        rendered = rendered.replace(key, value)
    return rendered


@st.dialog("Nueva versión de contrato", width="large", dismissible=False)
def _dialog_create_template() -> None:
    name = st.text_input("Nombre *", key="ctadm_new_name")
    version = st.text_input("Versión *", key="ctadm_new_version", placeholder="Ej. 1.0.0")
    is_active = st.checkbox("Activa", value=True, key="ctadm_new_active")
    content = st.text_area(
        "Texto del contrato *",
        height=240,
        key="ctadm_new_content",
        placeholder=(
            "Puedes usar variables:\n"
            "{{nombres}}, {{identificacion}}, {{numero_documento}}, {{fecha_expedicion}},\n"
            "{{nombre_tutor}}, {{identificacion_tutor}}, {{numero_documento_tutor}}, {{fecha_expedicion_tutor}}"
        ),
    )
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Crear versión", type="primary", use_container_width=True, key="ctadm_btn_create"):
            payload = {
                "name": name.strip(),
                "version": version.strip(),
                "content": content.strip(),
                "is_active": bool(is_active),
            }
            ok, code, data = api_client.post_template(payload)
            if ok:
                st.session_state["_ctadm_reload"] = True
                _close_dialogs()
                st.success("Versión creada.")
                st.rerun()
            else:
                st.error(f"HTTP {code}: {_detail(data)}")
    with c2:
        if st.button("Cancelar", use_container_width=True, key="ctadm_btn_cancel_create"):
            _close_dialogs()
            st.rerun()


@st.dialog("Editar versión de contrato", width="large", dismissible=False)
def _dialog_edit_template(template_id: int) -> None:
    ok, code, data = api_client.get_template(template_id)
    if not ok or not isinstance(data, dict):
        st.error(f"No se pudo cargar la plantilla (HTTP {code}): {_detail(data)}")
        if st.button("Cerrar", use_container_width=True, key="ctadm_btn_close_edit_err"):
            _close_dialogs()
            st.rerun()
        return

    name = st.text_input("Nombre *", value=data.get("name", ""), key=f"ctadm_edit_name_{template_id}")
    version = st.text_input(
        "Versión *", value=data.get("version", ""), key=f"ctadm_edit_version_{template_id}"
    )
    is_active = st.checkbox(
        "Activa", value=bool(data.get("is_active", True)), key=f"ctadm_edit_active_{template_id}"
    )
    content = st.text_area(
        "Texto del contrato *",
        value=data.get("content", ""),
        height=260,
        key=f"ctadm_edit_content_{template_id}",
    )
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Guardar cambios", type="primary", use_container_width=True, key=f"ctadm_btn_save_{template_id}"):
            payload = {
                "name": name.strip(),
                "version": version.strip(),
                "content": content.strip(),
                "is_active": bool(is_active),
            }
            ok_u, code_u, data_u = api_client.put_template(template_id, payload)
            if ok_u:
                st.session_state["_ctadm_reload"] = True
                _close_dialogs()
                st.success("Versión actualizada.")
                st.rerun()
            else:
                st.error(f"HTTP {code_u}: {_detail(data_u)}")
    with c2:
        if st.button("Cancelar", use_container_width=True, key=f"ctadm_btn_cancel_{template_id}"):
            _close_dialogs()
            st.rerun()


def render_contract_admin_tab() -> None:
    st.subheader("Administrador de contratos")
    st.caption("Gestiona versiones de plantillas y genera texto final con datos personales del cliente.")

    if "_ctadm_reload" not in st.session_state:
        st.session_state["_ctadm_reload"] = True
    if "_ctadm_only_active" not in st.session_state:
        st.session_state["_ctadm_only_active"] = False
    if "_ctadm_templates" not in st.session_state:
        st.session_state["_ctadm_templates"] = []
    if "_ctadm_selected_template_id" not in st.session_state:
        st.session_state["_ctadm_selected_template_id"] = None
    if "_ctadm_customer_row" not in st.session_state:
        st.session_state["_ctadm_customer_row"] = None
    if "_ctadm_rendered_text" not in st.session_state:
        st.session_state["_ctadm_rendered_text"] = ""
    if "ctadm_rendered_output" not in st.session_state:
        st.session_state["ctadm_rendered_output"] = ""

    r1, r2, r3 = st.columns([1.2, 1.2, 1.0])
    with r1:
        if st.button("➕ Nueva versión", type="primary", use_container_width=True, key="ctadm_btn_new"):
            st.session_state["_ctadm_dlg"] = "create"
    with r2:
        st.checkbox("Solo activas", key="_ctadm_only_active")
    with r3:
        if st.button("Actualizar listado", use_container_width=True, key="ctadm_btn_refresh"):
            st.session_state["_ctadm_reload"] = True

    if st.session_state.get("_ctadm_reload"):
        _load_templates(only_active=bool(st.session_state.get("_ctadm_only_active")))
        st.session_state["_ctadm_reload"] = False

    if st.session_state.get("_ctadm_error"):
        st.error(st.session_state["_ctadm_error"])

    templates = list(st.session_state.get("_ctadm_templates") or [])
    st.markdown(f"**Versiones registradas:** {len(templates)}")

    h1, h2, h3, h4, h5, h6 = st.columns([2.2, 1.0, 0.9, 0.9, 0.9, 0.9])
    h1.markdown("**Nombre**")
    h2.markdown("**Versión**")
    h3.markdown("**Activa**")
    h4.markdown("**Usar**")
    h5.markdown("**Editar**")
    h6.markdown("**Eliminar**")

    for item in templates:
        tid = int(item.get("id"))
        c1, c2, c3, c4, c5, c6 = st.columns([2.2, 1.0, 0.9, 0.9, 0.9, 0.9])
        c1.write(item.get("name", ""))
        c2.write(item.get("version", ""))
        c3.write("Sí" if item.get("is_active") else "No")
        with c4:
            if st.button("Usar", key=f"ctadm_use_{tid}", use_container_width=True):
                st.session_state["_ctadm_selected_template_id"] = tid
        with c5:
            if st.button("Editar", key=f"ctadm_edit_{tid}", use_container_width=True):
                st.session_state["_ctadm_dlg"] = "edit"
                st.session_state["_ctadm_dlg_id"] = tid
        with c6:
            if st.button("Eliminar", key=f"ctadm_del_{tid}", use_container_width=True):
                ok_d, code_d, data_d = api_client.delete_template(tid)
                if ok_d:
                    st.session_state["_ctadm_reload"] = True
                    st.success("Versión eliminada.")
                    st.rerun()
                else:
                    st.error(f"HTTP {code_d}: {_detail(data_d)}")

    st.divider()
    st.markdown("### Generar texto de contrato")
    st.caption(
        "Variables soportadas: "
        "`{{nombres}}`, `{{identificacion}}`, `{{numero_documento}}`, `{{fecha_expedicion}}`, "
        "`{{nombre_tutor}}`, `{{identificacion_tutor}}`, `{{numero_documento_tutor}}`, `{{fecha_expedicion_tutor}}`."
    )

    g1, g2 = st.columns([1.7, 1.0])
    with g1:
        doc = st.text_input("Documento del cliente para precargar datos", key="ctadm_doc_lookup")
    with g2:
        st.write("")
        if st.button("Buscar cliente", type="primary", use_container_width=True, key="ctadm_btn_lookup"):
            ok_c, msg_c, row = _fetch_customer_by_document(doc)
            if ok_c and row:
                st.session_state["_ctadm_customer_row"] = row
                st.success("Cliente cargado.")
            else:
                st.session_state["_ctadm_customer_row"] = None
                st.error(msg_c)

    selected_id = st.session_state.get("_ctadm_selected_template_id")
    if selected_id is None and templates:
        selected_id = int(templates[0].get("id"))
        st.session_state["_ctadm_selected_template_id"] = selected_id

    if templates:
        template_options = {int(t["id"]): f"{t.get('name')} · v{t.get('version')}" for t in templates}
        selected_id = st.selectbox(
            "Versión a usar",
            options=list(template_options.keys()),
            index=list(template_options.keys()).index(selected_id) if selected_id in template_options else 0,
            format_func=lambda x: template_options[x],
            key="ctadm_template_select",
        )
        st.session_state["_ctadm_selected_template_id"] = selected_id

    c_row = st.session_state.get("_ctadm_customer_row")
    if c_row:
        st.caption(
            "Cliente: "
            f"{c_row.get('first_name', '')} {c_row.get('last_name', '')} · "
            f"{c_row.get('document_type', '')} {c_row.get('document_number', '')}"
        )

    if st.button("Generar texto final", use_container_width=True, key="ctadm_btn_render"):
        if not c_row:
            st.error("Primero busca y confirma un cliente por documento.")
        elif not selected_id:
            st.error("Selecciona una versión de contrato.")
        else:
            ok_t, code_t, data_t = api_client.get_template(int(selected_id))
            if not ok_t or not isinstance(data_t, dict):
                st.error(f"No se pudo cargar plantilla (HTTP {code_t}): {_detail(data_t)}")
            else:
                rendered_text = _render_contract_text(
                    str(data_t.get("content", "")), c_row
                )
                st.session_state["_ctadm_rendered_text"] = rendered_text
                st.session_state["ctadm_rendered_output"] = rendered_text

    rendered = st.session_state.get("_ctadm_rendered_text", "")
    st.text_area("Texto final editable", height=260, key="ctadm_rendered_output")

    if rendered:
        # Botón de copiar al portapapeles en cliente (browser)
        js_text = json.dumps(rendered)
        components.html(
            f"""
            <button style="border-radius:999px;padding:8px 14px;background:#1f1f1f;color:#fff;border:1px solid #555;cursor:pointer"
                    onclick='navigator.clipboard.writeText({js_text}); this.innerText="Texto copiado";'>
              Copiar texto
            </button>
            """,
            height=48,
        )

    dlg = st.session_state.get("_ctadm_dlg")
    if dlg == "create":
        _dialog_create_template()
    elif dlg == "edit" and st.session_state.get("_ctadm_dlg_id"):
        _dialog_edit_template(int(st.session_state.get("_ctadm_dlg_id")))

