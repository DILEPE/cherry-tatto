"""Streamlit: administrador de plantillas de contrato (tatuaje / piercing)."""
from __future__ import annotations

from typing import Any, Dict

import streamlit as st

from app.domain.contract_kinds import KIND_LABEL_ES
from streamlit_app import api_client
from streamlit_app.rich_text import contract_rich_editor


def _detail(payload: Any) -> str:
    if isinstance(payload, dict):
        return str(payload.get("detail", payload))
    return str(payload)


_CTADM_ACTION_INFO_KEY = "_ctadm_action_info"


def _queue_ctadm_success(msg: str) -> None:
    """Toast en el siguiente rerun (diálogo cerrado o acción fuera del modal)."""
    st.session_state[_CTADM_ACTION_INFO_KEY] = msg


def _render_ctadm_feedback() -> None:
    msg = st.session_state.pop(_CTADM_ACTION_INFO_KEY, None)
    if msg:
        st.toast(msg, icon="✅", duration="long")


def _close_dialogs() -> None:
    for k in ("_ctadm_dlg", "_ctadm_dlg_id", "_ctadm_edit_payload", "_ctadm_edit_id"):
        st.session_state.pop(k, None)


def _kind_label(code: str) -> str:
    return KIND_LABEL_ES.get(code, code)  # type: ignore[arg-type]


def _render_template_row_actions(item: Dict[str, Any]) -> None:
    tid = int(item.get("id", 0) or 0)
    nm = str(item.get("name", "") or "")
    vs = str(item.get("version", "") or "")
    kind = str(item.get("contract_kind") or "tattoo")
    nm_short = nm[:72] + ("…" if len(nm) > 72 else "")

    def _dispatch_edit() -> None:
        st.session_state.pop(f"ctadm_edit_quill_{tid}", None)
        st.session_state.pop("_ctadm_edit_payload", None)
        st.session_state.pop("_ctadm_edit_id", None)
        st.session_state["_ctadm_dlg"] = "edit"
        st.session_state["_ctadm_dlg_id"] = tid
        st.rerun()

    pop = getattr(st, "popover", None)
    if pop:
        with pop("Acciones", use_container_width=True):
            if tid > 0:
                st.caption(f"Plantilla #{tid}")
                st.caption(f"{_kind_label(kind)} · {nm_short or '—'} · v{vs or '?'}")
            if st.button("Editar", key=f"ctadm_pop_edit_{tid}", use_container_width=True):
                _dispatch_edit()
            if st.button("Eliminar", key=f"ctadm_pop_del_{tid}", use_container_width=True):
                ok_d, code_d, data_d = api_client.delete_template(tid)
                if ok_d:
                    st.session_state["_ctadm_reload"] = True
                    _queue_ctadm_success("Versión eliminada.")
                    st.rerun()
                else:
                    st.toast(f"No se pudo eliminar (HTTP {code_d}): {_detail(data_d)}", icon="❌", duration="long")
        return

    ln1, ln2 = st.columns(2)
    with ln1:
        if st.button("Editar", key=f"ctadm_fb_edit_{tid}", use_container_width=True):
            _dispatch_edit()
    with ln2:
        if st.button("Eliminar", key=f"ctadm_fb_del_{tid}", use_container_width=True):
            ok_d, code_d, data_d = api_client.delete_template(tid)
            if ok_d:
                st.session_state["_ctadm_reload"] = True
                _queue_ctadm_success("Versión eliminada.")
                st.rerun()
            else:
                st.toast(f"No se pudo eliminar (HTTP {code_d}): {_detail(data_d)}", icon="❌", duration="long")


def _load_templates(*, only_active: bool) -> None:
    ok, code, data = api_client.get_templates(only_active=only_active)
    if ok and isinstance(data, list):
        st.session_state["_ctadm_templates"] = data
        st.session_state["_ctadm_error"] = None
    else:
        st.session_state["_ctadm_templates"] = []
        st.session_state["_ctadm_error"] = f"HTTP {code}: {_detail(data)}"


@st.dialog("Nueva versión de contrato", width="large", dismissible=False)
def _dialog_create_template() -> None:
    name = st.text_input("Nombre *", key="ctadm_new_name")
    kind = st.selectbox(
        "Tipo de trabajo *",
        options=["tattoo", "piercing"],
        format_func=_kind_label,
        key="ctadm_new_kind",
    )
    version = st.text_input("Versión *", key="ctadm_new_version", placeholder="Ej. 1.0.0")
    is_active = st.checkbox("Activa", value=True, key="ctadm_new_active")
    content = contract_rich_editor(
        label="Texto del contrato *",
        value="",
        key="ctadm_new_quill",
        show_placeholders=True,
    )
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Crear versión", type="primary", use_container_width=True, key="ctadm_btn_create"):
            payload = {
                "name": name.strip(),
                "contract_kind": kind,
                "version": version.strip(),
                "content": content,
                "is_active": bool(is_active),
            }
            ok, code, data = api_client.post_template(payload)
            if ok:
                st.session_state.pop("ctadm_new_quill", None)
                st.session_state["_ctadm_reload"] = True
                _queue_ctadm_success("Versión creada.")
                _close_dialogs()
                st.rerun()
            else:
                st.error(f"HTTP {code}: {_detail(data)}")
    with c2:
        if st.button("Cancelar", use_container_width=True, key="ctadm_btn_cancel_create"):
            st.session_state.pop("ctadm_new_quill", None)
            _close_dialogs()
            st.rerun()


@st.dialog("Editar versión de contrato", width="large", dismissible=False)
def _dialog_edit_template(template_id: int) -> None:
    if (
        "_ctadm_edit_payload" not in st.session_state
        or int(st.session_state.get("_ctadm_edit_id") or 0) != template_id
    ):
        with st.spinner("Cargando contrato…"):
            ok, code, data = api_client.get_template(template_id)
        if not ok or not isinstance(data, dict):
            st.error(f"No se pudo cargar la plantilla (HTTP {code}): {_detail(data)}")
            if st.button("Cerrar", use_container_width=True, key="ctadm_btn_close_edit_err"):
                _close_dialogs()
                st.rerun()
            return
        st.session_state["_ctadm_edit_payload"] = data
        st.session_state["_ctadm_edit_id"] = template_id

    data = st.session_state["_ctadm_edit_payload"]

    name = st.text_input("Nombre *", value=data.get("name", ""), key=f"ctadm_edit_name_{template_id}")
    cur_k = str(data.get("contract_kind") or "tattoo")
    kind = st.selectbox(
        "Tipo de trabajo *",
        options=["tattoo", "piercing"],
        index=0 if cur_k == "tattoo" else 1,
        format_func=_kind_label,
        key=f"ctadm_edit_kind_{template_id}",
    )
    version = st.text_input(
        "Versión *", value=data.get("version", ""), key=f"ctadm_edit_version_{template_id}"
    )
    is_active = st.checkbox(
        "Activa", value=bool(data.get("is_active", True)), key=f"ctadm_edit_active_{template_id}"
    )
    quill_key = f"ctadm_edit_quill_{template_id}"
    content = contract_rich_editor(
        label="Texto del contrato *",
        value=str(data.get("content") or ""),
        key=quill_key,
        show_placeholders=True,
    )
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Guardar cambios", type="primary", use_container_width=True, key=f"ctadm_btn_save_{template_id}"):
            payload = {
                "name": name.strip(),
                "contract_kind": kind,
                "version": version.strip(),
                "content": content,
                "is_active": bool(is_active),
            }
            ok_u, code_u, data_u = api_client.put_template(template_id, payload)
            if ok_u:
                st.session_state.pop(quill_key, None)
                st.session_state["_ctadm_reload"] = True
                _queue_ctadm_success("Versión actualizada.")
                _close_dialogs()
                st.rerun()
            else:
                st.error(f"HTTP {code_u}: {_detail(data_u)}")
    with c2:
        if st.button("Cancelar", use_container_width=True, key=f"ctadm_btn_cancel_{template_id}"):
            st.session_state.pop(quill_key, None)
            _close_dialogs()
            st.rerun()


def render_contract_admin_tab() -> None:
    st.subheader("Gestión de contratos")

    if "_ctadm_reload" not in st.session_state:
        st.session_state["_ctadm_reload"] = True
    if "_ctadm_only_active" not in st.session_state:
        st.session_state["_ctadm_only_active"] = False
    if "_ctadm_templates" not in st.session_state:
        st.session_state["_ctadm_templates"] = []

    r1, r2, r3 = st.columns([1.2, 1.2, 1.0])
    with r1:
        if st.button("➕ Nueva versión", type="primary", use_container_width=True, key="ctadm_btn_new"):
            st.session_state.pop("ctadm_new_quill", None)
            st.session_state["_ctadm_dlg"] = "create"
    with r2:
        st.checkbox("Solo activas", key="_ctadm_only_active")
    with r3:
        if st.button("Actualizar listado", use_container_width=True, key="ctadm_btn_refresh"):
            st.session_state["_ctadm_reload"] = True

    if st.session_state.get("_ctadm_reload"):
        with st.spinner("Cargando plantillas…"):
            _load_templates(only_active=bool(st.session_state.get("_ctadm_only_active")))
        st.session_state["_ctadm_reload"] = False

    _render_ctadm_feedback()

    if st.session_state.get("_ctadm_error"):
        st.error(st.session_state["_ctadm_error"])

    templates = list(st.session_state.get("_ctadm_templates") or [])
    st.markdown(f"**Versiones registradas:** {len(templates)}")

    st.markdown(
        """
        <style>
          .ctadm-col-title {
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

    tpl_colw = [1.35, 1.12, 0.94, 1.12, 1.52]
    h1, h2, h3, h4, h5 = st.columns(tpl_colw)
    h1.markdown('<span class="ctadm-col-title">Nombre</span>', unsafe_allow_html=True)
    h2.markdown('<span class="ctadm-col-title">Tipo</span>', unsafe_allow_html=True)
    h3.markdown('<span class="ctadm-col-title">Versión</span>', unsafe_allow_html=True)
    h4.markdown('<span class="ctadm-col-title">Activa</span>', unsafe_allow_html=True)
    h5.markdown('<span class="ctadm-col-title">Acciones</span>', unsafe_allow_html=True)

    for item in templates:
        c1, c2, c3, c4, c5 = st.columns(tpl_colw)
        c1.write(item.get("name", ""))
        c2.write(_kind_label(str(item.get("contract_kind") or "tattoo")))
        c3.write(item.get("version", ""))
        c4.write("Sí" if item.get("is_active") else "No")
        with c5:
            _render_template_row_actions(item)

    dlg = st.session_state.get("_ctadm_dlg")
    if dlg == "create":
        _dialog_create_template()
    elif dlg == "edit" and st.session_state.get("_ctadm_dlg_id"):
        _dialog_edit_template(int(st.session_state.get("_ctadm_dlg_id")))
