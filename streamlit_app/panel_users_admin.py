"""Streamlit: gestión de usuarios del panel (mismo esquema visual que clientes y citas)."""
from __future__ import annotations

from typing import Any, Dict, List

import streamlit as st

from app.domain.panel_modules import ASSIGNABLE_PANEL_MODULE_KEYS, PANEL_MODULE_LABEL_ES
from app.domain.panel_user_profile import PANEL_ROLE_CHOICES, PANEL_ROLE_LABEL_ES
from streamlit_app import api_client
from streamlit_app.store_choices import load_store_choices, store_display_label
from streamlit_app.panel_auth import panel_invalidate_module_cache, panel_is_operator_admin


def _detail(payload: Any) -> str:
    if isinstance(payload, dict):
        det = payload.get("detail")
        if det is None:
            return str(payload)
        if isinstance(det, list):
            parts: list[str] = []
            for item in det:
                if isinstance(item, dict):
                    loc = item.get("loc") or item.get("location")
                    msg = item.get("msg") or item.get("message") or item
                    parts.append(f"{loc}: {msg}" if loc else str(msg))
                else:
                    parts.append(str(item))
            return "; ".join(parts) if parts else str(payload)
        return str(det)
    return str(payload)


_PU_ACTION_INFO_KEY = "_pu_action_info"
_PU_ACTION_WARN_KEY = "_pu_action_warn"


def _queue_pu_success(msg: str) -> None:
    """Confirmación en el siguiente rerun (tras cerrar el diálogo)."""
    st.session_state[_PU_ACTION_INFO_KEY] = msg


def _queue_pu_warning(msg: str) -> None:
    """Aviso complementario (p. ej. fallo al guardar módulos tras crear/editar usuario)."""
    st.session_state[_PU_ACTION_WARN_KEY] = msg


def _render_pu_feedback() -> None:
    warn = st.session_state.pop(_PU_ACTION_WARN_KEY, None)
    if warn:
        st.toast(warn, icon="⚠️", duration="long")
    msg = st.session_state.pop(_PU_ACTION_INFO_KEY, None)
    if msg:
        st.toast(msg, icon="✅", duration="long")


def _fetch_panel_users() -> None:
    ok, code, data = api_client.get_panel_users()
    if ok and isinstance(data, list):
        st.session_state["_pu_list"] = data
        st.session_state["_pu_last_error"] = None
    else:
        st.session_state["_pu_list"] = None
        st.session_state["_pu_last_error"] = (code, _detail(data))


def _inject_pu_table_styles() -> None:
    """Mismas cabeceras de columna que en `customers_management`."""
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


def _close_pu_dialogs() -> None:
    for k in (
        "_pu_dlg",
        "_pu_dlg_id",
        "_pu_dlg_edit",
        "_pu_dlg_edit_id",
    ):
        st.session_state.pop(k, None)


def _reset_pu_create_keys() -> None:
    for k in (
        "dlg_pu_fn",
        "dlg_pu_ln",
        "dlg_pu_user",
        "dlg_pu_pass",
        "dlg_pu_addr",
        "dlg_pu_phone",
        "dlg_pu_store",
        "dlg_pu_role",
        "dlg_pu_active",
        "dlg_pu_mod",
    ):
        st.session_state.pop(k, None)


def _render_panel_user_row_actions(uid: int, etiqueta: str, *, is_active: bool) -> None:
    def _go_edit() -> None:
        st.session_state["_pu_dlg"] = "edit"
        st.session_state["_pu_dlg_id"] = uid
        st.session_state.pop("_pu_dlg_edit", None)
        st.session_state.pop("_pu_dlg_edit_id", None)

    me_raw = st.session_state.get("_panel_user_id")
    is_me = me_raw is not None and int(me_raw) == int(uid)

    def _apply_active(new_active: bool) -> None:
        with st.spinner("Actualizando estado…"):
            ok, code, raw = api_client.patch_panel_user(uid, {"is_active": new_active})
        if ok:
            if is_me:
                panel_invalidate_module_cache()
                if not new_active:
                    _queue_pu_warning(
                        "Has desactivado tu propio usuario: cuando salgas del panel no podrás iniciar sesión hasta que otro administrador te reactive."
                    )
            _queue_pu_success("Usuario desactivado." if not new_active else "Usuario activado.")
            st.session_state["_pu_reload"] = True
            st.rerun()
        else:
            st.toast(f"No se pudo cambiar el estado (HTTP {code}): {_detail(raw)}", icon="❌", duration="long")

    pop = getattr(st, "popover", None)
    if pop:
        with pop("Acciones", use_container_width=True):
            if uid > 0:
                st.caption(f"Usuario #{uid}")
            if etiqueta:
                st.caption(etiqueta[:80] + ("…" if len(etiqueta) > 80 else ""))
            if not is_active:
                if st.button("Activar", key=f"pu_act_{uid}", use_container_width=True):
                    _apply_active(True)
            else:
                if st.button("Desactivar", key=f"pu_deact_{uid}", use_container_width=True):
                    _apply_active(False)
            if st.button("Editar", key=f"pu_e_{uid}", use_container_width=True):
                _go_edit()
        return

    row_act, row_ed = st.columns(2)
    with row_act:
        if not is_active:
            if st.button("Activar", key=f"pu_fb_act_{uid}", use_container_width=True):
                _apply_active(True)
        else:
            if st.button("Desactivar", key=f"pu_fb_deact_{uid}", use_container_width=True):
                _apply_active(False)
    with row_ed:
        if st.button("Editar", key=f"pu_fb_e_{uid}", use_container_width=True):
            _go_edit()


@st.dialog("Registrar usuario del panel", width="large", dismissible=False)
def _dialog_crear_usuario_panel() -> None:
    st.markdown("##### Datos del operador")
    st.caption("Usuario de acceso: minúsculas, números, `.`, `_`, `-` (mín. 3 caracteres). Contraseña mín. 8 caracteres.")
    a, b = st.columns(2)
    with a:
        w_fn = st.text_input("Nombre", key="dlg_pu_fn")
        w_ln = st.text_input("Apellido", key="dlg_pu_ln")
        w_user = st.text_input("Usuario (login) *", key="dlg_pu_user")
        w_pass = st.text_input("Contraseña *", type="password", key="dlg_pu_pass")
    with b:
        w_addr = st.text_input("Dirección", key="dlg_pu_addr")
        w_phone = st.text_input("Celular", key="dlg_pu_phone")
        store_ids, store_labels = load_store_choices()
        w_store = st.selectbox(
            "Tienda *",
            options=store_ids,
            format_func=lambda x: store_display_label(int(x), store_labels),
            key="dlg_pu_store",
        )
        w_role = st.selectbox(
            "Rol *",
            options=list(PANEL_ROLE_CHOICES),
            format_func=lambda x: PANEL_ROLE_LABEL_ES[str(x)],
            key="dlg_pu_role",
        )
    w_active = st.checkbox("Usuario activo", value=True, key="dlg_pu_active")
    st.markdown("##### Acceso a módulos del panel")
    st.caption(
        "Si el rol es **administrador**, no aplica: verá todas las pestañas. "
        "Para otros roles, elige qué secciones verán al entrar al panel."
    )
    w_mods = st.multiselect(
        "Módulos permitidos",
        options=list(ASSIGNABLE_PANEL_MODULE_KEYS),
        format_func=lambda k: PANEL_MODULE_LABEL_ES.get(k, k),
        default=[],
        key="dlg_pu_mod",
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Registrar usuario", type="primary", use_container_width=True, key="dlg_pu_submit"):
            u = (w_user or "").strip().lower()
            if len(u) < 3:
                st.error("El usuario debe tener al menos 3 caracteres válidos.")
                return
            if len(w_pass or "") < 8:
                st.error("La contraseña debe tener al menos 8 caracteres.")
                return
            body: Dict[str, Any] = {
                "username": u,
                "password": w_pass,
                "first_name": (w_fn or "").strip(),
                "last_name": (w_ln or "").strip(),
                "store_id": int(w_store),
                "role": w_role,
                "is_active": bool(w_active),
            }
            ad = (w_addr or "").strip()
            ph = (w_phone or "").strip()
            if ad:
                body["address"] = ad
            if ph:
                body["phone"] = ph
            with st.spinner("Registrando usuario…"):
                ok, code, raw = api_client.post_panel_user_create(body)
                if ok:
                    new_id: Any = None
                    if isinstance(raw, dict):
                        new_id = raw.get("id")
                    ok_m, c_m, r_m = True, 0, None
                    if w_role != "administrador" and new_id is not None:
                        ok_m, c_m, r_m = api_client.put_panel_user_modules(int(new_id), list(w_mods))
            if ok:
                if w_role != "administrador" and new_id is not None and not ok_m:
                    _queue_pu_warning(
                        "Usuario creado, pero no se pudieron guardar los módulos "
                        f"(HTTP {c_m}): {_detail(r_m)}"
                    )
                _queue_pu_success("Usuario registrado correctamente.")
                st.session_state["_pu_reload"] = True
                _reset_pu_create_keys()
                _close_pu_dialogs()
                st.rerun()
            elif code == 409:
                st.error(_detail(raw))
            else:
                st.error(f"No se pudo registrar (HTTP {code}): {_detail(raw)}")
    with c2:
        if st.button("Cancelar", use_container_width=True, key="dlg_pu_cancel"):
            _reset_pu_create_keys()
            _close_pu_dialogs()
            st.rerun()


@st.dialog("Editar usuario del panel", width="large", dismissible=False)
def _dialog_editar_usuario_panel(user_id: int) -> None:
    if "_pu_dlg_edit" not in st.session_state or st.session_state.get("_pu_dlg_edit_id") != user_id:
        with st.spinner("Cargando usuario…"):
            ok, code, data = api_client.get_panel_user(user_id)
        if not ok or not isinstance(data, dict):
            st.error(f"No se pudo cargar (HTTP {code}): {_detail(data)}")
            if st.button("Cerrar", key="dlg_pu_ed_err"):
                _close_pu_dialogs()
                st.session_state.pop("_pu_dlg_edit", None)
                st.session_state.pop("_pu_dlg_edit_id", None)
                st.rerun()
            return
        st.session_state["_pu_dlg_edit"] = data
        st.session_state["_pu_dlg_edit_id"] = user_id

    ed = st.session_state["_pu_dlg_edit"]
    st.markdown("##### Datos del operador")

    a, b = st.columns(2)
    with a:
        e_fn = st.text_input("Nombre", value=str(ed.get("first_name") or ""), key="dlg_pu_e_fn")
        e_ln = st.text_input("Apellido", value=str(ed.get("last_name") or ""), key="dlg_pu_e_ln")
        st.text_input("Usuario (no editable)", value=str(ed.get("username") or ""), disabled=True, key="dlg_pu_e_user_ro")
    with b:
        e_addr = st.text_input("Dirección", value=str(ed.get("address") or ""), key="dlg_pu_e_addr")
        e_phone = st.text_input("Celular", value=str(ed.get("phone") or ""), key="dlg_pu_e_phone")
        try:
            store_ids_e, store_labels_e = load_store_choices()
            cur_sid = int(ed.get("store_id") or 0)
            s_idx = store_ids_e.index(cur_sid) if cur_sid in store_ids_e else 0
        except (TypeError, ValueError):
            store_ids_e, store_labels_e = load_store_choices()
            s_idx = 0
        e_store = st.selectbox(
            "Tienda",
            options=store_ids_e,
            index=s_idx,
            format_func=lambda x: store_display_label(int(x), store_labels_e),
            key="dlg_pu_e_store",
        )
        try:
            r_idx = list(PANEL_ROLE_CHOICES).index(str(ed.get("role") or "vendedor"))
        except ValueError:
            r_idx = 1
        e_role = st.selectbox(
            "Rol",
            options=list(PANEL_ROLE_CHOICES),
            index=r_idx,
            format_func=lambda x: PANEL_ROLE_LABEL_ES[str(x)],
            key="dlg_pu_e_role",
        )
    e_active = st.checkbox("Usuario activo", value=bool(ed.get("is_active", True)), key="dlg_pu_e_active")
    e_pass = st.text_input(
        "Nueva contraseña (opcional)",
        type="password",
        key="dlg_pu_e_pass",
        help="Mínimo 8 caracteres si la cambias.",
    )
    e_mods: List[str] = []
    if str(e_role) == "administrador":
        st.info("Los administradores tienen acceso completo al panel (todas las pestañas y esta gestión de usuarios).")
    else:
        ok_g, _, raw_g = api_client.get_panel_user_module_grants(user_id)
        grants: List[str] = []
        if ok_g and isinstance(raw_g, list):
            grants = [str(x) for x in raw_g if str(x) in ASSIGNABLE_PANEL_MODULE_KEYS]
        st.markdown("##### Acceso a módulos del panel")
        e_mods = st.multiselect(
            "Módulos permitidos (pestañas)",
            options=list(ASSIGNABLE_PANEL_MODULE_KEYS),
            format_func=lambda k: PANEL_MODULE_LABEL_ES.get(k, k),
            default=grants,
            key=f"dlg_pu_e_mod_{user_id}",
        )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Guardar cambios", type="primary", use_container_width=True, key="dlg_pu_e_save"):
            if e_pass and len(e_pass) < 8:
                st.error("Si cambias la contraseña, debe tener al menos 8 caracteres.")
            else:
                patch: Dict[str, Any] = {
                    "first_name": (e_fn or "").strip(),
                    "last_name": (e_ln or "").strip(),
                    "address": (e_addr or "").strip() or None,
                    "phone": (e_phone or "").strip() or None,
                    "store_id": int(e_store),
                    "role": e_role,
                    "is_active": bool(e_active),
                }
                if e_pass:
                    patch["password"] = e_pass
                with st.spinner("Guardando cambios…"):
                    ok, code, raw = api_client.patch_panel_user(user_id, patch)
                    ok_m, c_m, r_m = True, 0, None
                    if ok and str(e_role) != "administrador":
                        ok_m, c_m, r_m = api_client.put_panel_user_modules(user_id, list(e_mods))
                if ok:
                    if str(e_role) != "administrador" and not ok_m:
                        _queue_pu_warning(
                            "Datos guardados, pero no se actualizaron los módulos "
                            f"(HTTP {c_m}): {_detail(r_m)}"
                        )
                    sid = st.session_state.get("_panel_user_id")
                    if sid is not None and int(sid) == int(user_id):
                        panel_invalidate_module_cache()
                    _queue_pu_success("Usuario actualizado.")
                    st.session_state["_pu_reload"] = True
                    st.session_state.pop("_pu_dlg_edit", None)
                    st.session_state.pop("_pu_dlg_edit_id", None)
                    _close_pu_dialogs()
                    st.rerun()
                elif code == 404:
                    st.error("Usuario no encontrado.")
                else:
                    st.error(f"No se pudo actualizar (HTTP {code}): {_detail(raw)}")
    with c2:
        if st.button("Cancelar", use_container_width=True, key="dlg_pu_e_cancel"):
            st.session_state.pop("_pu_dlg_edit", None)
            st.session_state.pop("_pu_dlg_edit_id", None)
            _close_pu_dialogs()
            st.rerun()


def render_panel_users_tab() -> None:
    if not panel_is_operator_admin():
        st.warning("No tienes permiso para gestionar usuarios del panel.")
        return

    st.subheader("Gestión de usuarios del panel")
    with st.expander("Administración de acceso a módulos", expanded=False):
        st.markdown(
            "- El rol **administrador** ve **todas** las pestañas, incluida esta de usuarios, y puede "
            "**activar y desactivar** cuentas desde **Acciones** en cada fila (un usuario inactivo no puede iniciar sesión).\n"
            "- **Vendedor**, **perforador** y **tatuador** solo ven las pestañas que marques en **Editar** "
            "(o al **Crear**) en **Módulos permitidos**.\n"
            "- Si un usuario no administrador no tiene módulos, verá un aviso al entrar al panel."
        )

    if "_pu_reload" not in st.session_state:
        st.session_state["_pu_reload"] = True

    r1, r2, r3, r4 = st.columns([2.2, 1, 0.8, 0.8])
    with r1:
        st.write("")
    with r2:
        st.write("")
        st.write("")
        if st.button("Actualizar", use_container_width=True, key="pu_btn_refresh"):
            st.session_state["_pu_reload"] = True
            st.rerun()
    with r3:
        st.write("")
    with r4:
        st.write("")
        st.write("")
        if st.button("➕ Crear", use_container_width=True, type="primary", key="pu_btn_create"):
            st.session_state["_pu_dlg"] = "create"

    if st.session_state.get("_pu_reload"):
        _fetch_panel_users()
        st.session_state["_pu_reload"] = False

    _render_pu_feedback()

    err = st.session_state.get("_pu_last_error")
    if err:
        st.error(f"Error al cargar listado (HTTP {err[0]}): {err[1]}")

    items: List[Dict[str, Any]] = list(st.session_state.get("_pu_list") or [])
    total = len(items)
    st.markdown(f"**{total}** usuario(s) del panel")

    _inject_pu_table_styles()
    pu_colw = [1.55, 1.05, 1.05, 1.15, 1.05, 0.55, 1.0]
    h1, h2, h3, h4, h5, h6, h7 = st.columns(pu_colw)
    h1.markdown('<span class="cust-col-title">Nombre</span>', unsafe_allow_html=True)
    h2.markdown('<span class="cust-col-title">Usuario</span>', unsafe_allow_html=True)
    h3.markdown('<span class="cust-col-title">Tienda</span>', unsafe_allow_html=True)
    h4.markdown('<span class="cust-col-title">Rol</span>', unsafe_allow_html=True)
    h5.markdown('<span class="cust-col-title">Celular</span>', unsafe_allow_html=True)
    h6.markdown('<span class="cust-col-title">Activo</span>', unsafe_allow_html=True)
    h7.markdown('<span class="cust-col-title">Acciones</span>', unsafe_allow_html=True)

    for it in items:
        uid = int(it.get("id", 0))
        nombre = f"{it.get('first_name', '')} {it.get('last_name', '')}".strip() or "—"
        usr = str(it.get("username") or "")
        tienda = str(it.get("store_name") or "").strip() or "—"
        rol = PANEL_ROLE_LABEL_ES.get(str(it.get("role")), str(it.get("role", "")))
        cel = str(it.get("phone") or "") or "—"
        activo = "Sí" if it.get("is_active") else "No"
        c1, c2, c3, c4, c5, c6, c7 = st.columns(pu_colw)
        with c1:
            st.write(nombre)
        with c2:
            st.write(usr)
        with c3:
            st.write(tienda)
        with c4:
            st.write(rol)
        with c5:
            st.write(cel)
        with c6:
            st.write(activo)
        with c7:
            _render_panel_user_row_actions(uid, nombre, is_active=bool(it.get("is_active")))

    st.divider()

    if total == 0 and not err:
        st.info("No hay usuarios. Pulsa **➕ Crear** o registra uno desde el login (**Crear cuenta**).")

    dlg = st.session_state.get("_pu_dlg")
    dlg_id = st.session_state.get("_pu_dlg_id")

    if dlg == "create":
        _dialog_crear_usuario_panel()
    elif dlg == "edit" and dlg_id:
        _dialog_editar_usuario_panel(int(dlg_id))
