"""Streamlit: gestión del catálogo de tiendas (solo administradores)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import streamlit as st

from streamlit_app import api_client
from streamlit_app.store_choices import invalidate_store_choices_cache, load_store_choices, store_display_label
from streamlit_app.theme import get_panel_theme


def _detail(payload: Any) -> str:
    if isinstance(payload, dict):
        return str(payload.get("detail", payload))
    return str(payload)


_STORE_ACTION_INFO_KEY = "_store_action_info"
_DLG_STORE_ROOT_HTML = '<div class="dlg-store-root" data-store-dlg="1" aria-hidden="true"></div>'
_STORE_TAB_ROOT_HTML = '<div class="store-tab-root" aria-hidden="true"></div>'


def _mark_store_dialog_scope() -> None:
    """Marcador para CSS de diálogo en modo claro (ver styles/_theme_stores.css)."""
    st.markdown(_DLG_STORE_ROOT_HTML, unsafe_allow_html=True)
    if get_panel_theme() == "light":
        st.markdown(
            """
            <style>
            div[data-testid="stDialog"]:has(.dlg-store-root) [role="dialog"],
            div[data-testid="stDialog"]:has([data-store-dlg]) [role="dialog"] {
              background: #ffffff !important;
              background-color: #ffffff !important;
              color: #1e293b !important;
            }
            div[data-testid="stDialog"]:has(.dlg-store-root) [data-testid="stWidgetLabel"] p,
            div[data-testid="stDialog"]:has(.dlg-store-root) [data-testid="stWidgetLabel"] label,
            div[data-testid="stDialog"]:has(.dlg-store-root) [data-testid="stCaptionContainer"] p {
              color: #334155 !important;
            }
            div[data-testid="stDialog"]:has(.dlg-store-root) [data-testid="stButton"] button[data-testid="baseButton-primary"],
            div[data-testid="stDialog"]:has(.dlg-store-root) [data-testid="stButton"] button[kind="primary"],
            div[data-testid="stDialog"]:has(.dlg-store-root) button[data-testid="baseButton-primary"][class*="st-emotion-cache"] {
              background-image: linear-gradient(180deg, #ff5fb8 0%, #ff007f 52%, #d90064 100%) !important;
              background-color: #ff007f !important;
              color: #ffffff !important;
            }
            div[data-testid="stDialog"]:has(.dlg-store-root) [data-testid="stButton"] button[data-testid="baseButton-primary"] *,
            div[data-testid="stDialog"]:has(.dlg-store-root) [data-testid="stButton"] button[kind="primary"] * {
              color: #ffffff !important;
              background: transparent !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )


def _queue_store_success(msg: str) -> None:
    st.session_state[_STORE_ACTION_INFO_KEY] = msg


def _render_store_feedback() -> None:
    msg = st.session_state.pop(_STORE_ACTION_INFO_KEY, None)
    if msg:
        st.toast(msg, icon="✅", duration="long")


def _fetch_stores() -> None:
    ok, code, data = api_client.get_stores(include_inactive=True)
    if ok and isinstance(data, list):
        st.session_state["_store_list"] = data
        st.session_state["_store_last_error"] = None
    else:
        st.session_state["_store_list"] = None
        st.session_state["_store_last_error"] = (code, _detail(data))


def _close_store_dialogs() -> None:
    for k in ("_store_dlg", "_store_dlg_id", "_store_dlg_name"):
        st.session_state.pop(k, None)


@st.dialog("Nueva tienda", width="medium", dismissible=False)
def _dialog_crear_tienda() -> None:
    _mark_store_dialog_scope()
    name = st.text_input("Nombre *", key="dlg_store_name")
    address = st.text_input("Dirección", key="dlg_store_address")
    phone = st.text_input("Teléfono", key="dlg_store_phone")
    email = st.text_input("Correo", key="dlg_store_email")
    active = st.checkbox("Activa", value=True, key="dlg_store_active")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Crear", type="primary", use_container_width=True, key="dlg_store_create_btn"):
            if not (name or "").strip():
                st.error("El nombre es obligatorio.")
            else:
                payload = {
                    "name": name.strip(),
                    "address": (address or "").strip() or None,
                    "phone": (phone or "").strip() or None,
                    "email": (email or "").strip() or None,
                    "is_active": bool(active),
                }
                with st.spinner("Guardando…"):
                    ok, http_code, data = api_client.post_store(payload)
                if ok:
                    invalidate_store_choices_cache()
                    _queue_store_success(f"**Tienda creada** · {payload['name']}")
                    _close_store_dialogs()
                    st.session_state["_store_reload"] = True
                    st.rerun()
                else:
                    st.error(f"Error HTTP {http_code}: {_detail(data)}")
    with c2:
        if st.button("Cancelar", use_container_width=True, key="dlg_store_create_cancel"):
            _close_store_dialogs()
            st.rerun()


@st.dialog("Editar tienda", width="medium", dismissible=False)
def _dialog_editar_tienda(store_id: int) -> None:
    _mark_store_dialog_scope()
    ok, code_http, data = api_client.get_store(store_id)
    if not ok or not isinstance(data, dict):
        st.error(f"No se pudo cargar la tienda (HTTP {code_http}): {_detail(data)}")
        if st.button("Cerrar", use_container_width=True):
            _close_store_dialogs()
            st.rerun()
        return
    st.caption(f"ID interno: **#{store_id}**")
    name = st.text_input("Nombre *", value=str(data.get("name") or ""), key="dlg_store_e_name")
    address = st.text_input("Dirección", value=str(data.get("address") or ""), key="dlg_store_e_addr")
    phone = st.text_input("Teléfono", value=str(data.get("phone") or ""), key="dlg_store_e_phone")
    email = st.text_input("Correo", value=str(data.get("email") or ""), key="dlg_store_e_email")
    active = st.checkbox(
        "Activa",
        value=bool(data.get("is_active", True)),
        key="dlg_store_e_active",
    )
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Guardar", type="primary", use_container_width=True, key="dlg_store_save_btn"):
            if not (name or "").strip():
                st.error("El nombre es obligatorio.")
            else:
                payload = {
                    "name": name.strip(),
                    "address": (address or "").strip() or None,
                    "phone": (phone or "").strip() or None,
                    "email": (email or "").strip() or None,
                    "is_active": bool(active),
                }
                with st.spinner("Guardando…"):
                    ok_s, http_s, body = api_client.put_store(store_id, payload)
                if ok_s:
                    invalidate_store_choices_cache()
                    _queue_store_success(f"**Tienda actualizada** · {payload['name']}")
                    _close_store_dialogs()
                    st.session_state["_store_reload"] = True
                    st.rerun()
                else:
                    st.error(f"Error HTTP {http_s}: {_detail(body)}")
    with c2:
        if st.button("Cancelar", use_container_width=True, key="dlg_store_edit_cancel"):
            _close_store_dialogs()
            st.rerun()


@st.dialog("Eliminar tienda", width="small", dismissible=False)
def _dialog_eliminar_tienda(store_id: int, nombre: str) -> None:
    _mark_store_dialog_scope()
    st.warning(
        f"¿Eliminar **{nombre}** del catálogo? "
        "No se puede si hay usuarios del panel asignados a esta tienda."
    )
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Eliminar", type="primary", use_container_width=True, key="dlg_store_del_ok"):
            with st.spinner("Eliminando…"):
                ok, http_code, data = api_client.delete_store(store_id)
            if ok:
                invalidate_store_choices_cache()
                _queue_store_success(f"**Tienda eliminada** · {nombre}")
                _close_store_dialogs()
                st.session_state["_store_reload"] = True
                st.rerun()
            else:
                st.error(f"Error HTTP {http_code}: {_detail(data)}")
    with c2:
        if st.button("Cancelar", use_container_width=True, key="dlg_store_del_cancel"):
            _close_store_dialogs()
            st.rerun()


def _render_store_row_actions(sid: int, nombre: str) -> None:
    """Casilla en línea con celdas internas e iconos (sin menú desplegable)."""
    c_edit, c_del = st.columns(2, gap="small", vertical_alignment="center")
    with c_edit:
        if st.button(
            "",
            key=f"store_edit_{sid}",
            help="Editar tienda",
            icon=":material/edit:",
            use_container_width=True,
        ):
            st.session_state["_store_dlg"] = "edit"
            st.session_state["_store_dlg_id"] = sid
            st.rerun()
    with c_del:
        if st.button(
            "",
            key=f"store_del_{sid}",
            help="Eliminar tienda",
            icon=":material/delete:",
            use_container_width=True,
        ):
            st.session_state["_store_dlg"] = "delete"
            st.session_state["_store_dlg_id"] = sid
            st.session_state["_store_dlg_name"] = nombre
            st.rerun()


def render_stores_management_tab() -> None:
    """Catálogo de tiendas: alta, edición y baja (administrador)."""
    st.markdown(_STORE_TAB_ROOT_HTML, unsafe_allow_html=True)
    st.subheader("Gestión de tiendas")
    st.caption(
        "Define las tiendas del negocio (Cherry Tattoo, Rock City, sucursales…). "
        "Los usuarios del panel eligen una tienda al registrarse o al editarlos en **Gestión de usuarios**."
    )

    if "_store_reload" not in st.session_state:
        st.session_state["_store_reload"] = True

    r1, r2, r3 = st.columns([2.5, 1, 1])
    with r2:
        st.write("")
        st.write("")
        if st.button("Actualizar", use_container_width=True, key="store_btn_refresh"):
            st.session_state["_store_reload"] = True
            st.rerun()
    with r3:
        st.write("")
        st.write("")
        if st.button("➕ Nueva tienda", type="primary", use_container_width=True, key="store_btn_create"):
            st.session_state["_store_dlg"] = "create"

    if st.session_state.get("_store_reload"):
        with st.spinner("Cargando tiendas…"):
            _fetch_stores()
        st.session_state["_store_reload"] = False

    _render_store_feedback()

    err = st.session_state.get("_store_last_error")
    if err:
        st.error(f"Error al cargar tiendas (HTTP {err[0]}): {err[1]}")
        if "stores" in str(err[1]).lower() or err[0] == 500:
            st.info("Aplica la migración SQL `sql/024_stores.sql` en MySQL y reinicia la API.")

    raw = st.session_state.get("_store_list")
    items: List[Dict[str, Any]] = list(raw) if isinstance(raw, list) else []
    st.markdown(f"**{len(items)}** tienda(s) en catálogo")

    colw = [1.5, 1.6, 1.0, 0.7, 1.15]
    h1, h2, h3, h4, h5 = st.columns(colw, vertical_alignment="center")
    h1.markdown('<span class="cust-col-title">Nombre</span>', unsafe_allow_html=True)
    h2.markdown('<span class="cust-col-title">Contacto</span>', unsafe_allow_html=True)
    h3.markdown('<span class="cust-col-title">Dirección</span>', unsafe_allow_html=True)
    h4.markdown('<span class="cust-col-title">Estado</span>', unsafe_allow_html=True)
    h5.markdown('<span class="cust-col-title">Acciones</span>', unsafe_allow_html=True)

    for it in items:
        sid = int(it.get("id") or 0)
        nombre = str(it.get("name") or "—")
        tel = str(it.get("phone") or "—")
        em = str(it.get("email") or "")
        contacto = tel if not em else f"{tel} · {em}" if tel != "—" else em
        activa = bool(it.get("is_active", True))
        c1, c2, c3, c4, c5 = st.columns(colw, vertical_alignment="center")
        c1.write(nombre)
        c2.write(contacto or "—")
        c3.write(str(it.get("address") or "—"))
        c4.write("Activa" if activa else "Inactiva")
        with c5:
            _render_store_row_actions(sid, nombre)

    dlg = st.session_state.get("_store_dlg")
    dlg_id = st.session_state.get("_store_dlg_id")
    if dlg == "create":
        _dialog_crear_tienda()
    elif dlg == "edit" and dlg_id:
        _dialog_editar_tienda(int(dlg_id))
    elif dlg == "delete" and dlg_id:
        _dialog_eliminar_tienda(int(dlg_id), str(st.session_state.get("_store_dlg_name") or ""))


__all__ = ["render_stores_management_tab"]
