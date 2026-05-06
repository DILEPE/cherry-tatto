"""
Autenticación del panel Streamlit.

- Modo **env** (`PANEL_AUTH_USERS_SOURCE=env` o sin definir): usuario/contraseña en `.env`.
- Modo **database**: usuarios en MySQL (`panel_users`), registro e inicio de sesión vía API.

Las vistas públicas (`?view=contract_sign` y `?view=contract_read`) no pasan por este gate.
"""
from __future__ import annotations

import hmac
import os
from typing import Any, Final

import streamlit as st

from app.domain.panel_modules import ASSIGNABLE_PANEL_MODULE_KEYS
from app.domain.panel_user_profile import (
    PANEL_ROLE_CHOICES,
    PANEL_ROLE_LABEL_ES,
    PANEL_STORE_CHOICES,
    PANEL_STORE_LABEL_ES,
)
from streamlit_app import api_client

_ENV_ON: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})


def panel_auth_enabled() -> bool:
    return os.getenv("PANEL_AUTH_ENABLED", "").strip().lower() in _ENV_ON


def panel_auth_users_from_database() -> bool:
    return os.getenv("PANEL_AUTH_USERS_SOURCE", "env").strip().lower() == "database"


def _credentials_ok() -> tuple[str, str] | None:
    user = os.getenv("PANEL_LOGIN_USER", "").strip()
    password = os.getenv("PANEL_LOGIN_PASSWORD", "").strip()
    if not user or not password:
        return None
    return user, password


def _safe_str_eq(a: str, b: str) -> bool:
    try:
        ae, be = a.encode("utf-8"), b.encode("utf-8")
        if len(ae) != len(be):
            return False
        return hmac.compare_digest(ae, be)
    except (UnicodeEncodeError, TypeError):
        return False


def _clear_db_panel_identity() -> None:
    for k in (
        "_panel_user_id",
        "_panel_username",
        "_panel_user_role",
        "_panel_module_keys_cache",
    ):
        st.session_state.pop(k, None)


def _set_env_operator_session() -> None:
    st.session_state["_panel_session_full_access"] = True
    _clear_db_panel_identity()


def _set_db_operator_session(user: dict[str, Any]) -> None:
    st.session_state["_panel_session_full_access"] = False
    st.session_state["_panel_user_id"] = int(user["id"])
    st.session_state["_panel_username"] = str(user.get("username", ""))
    st.session_state["_panel_user_role"] = str(user.get("role", ""))
    st.session_state.pop("_panel_module_keys_cache", None)


def panel_is_operator_admin() -> bool:
    """Administrador de negocio: gestión de usuarios, permisos y todos los módulos."""
    if not panel_auth_enabled():
        return True
    if st.session_state.get("_panel_session_full_access"):
        return True
    return st.session_state.get("_panel_user_role") == "administrador"


def panel_allowed_module_keys() -> frozenset[str]:
    """Claves de módulos operativos visibles (excluye la pestaña de usuarios, solo para administradores)."""
    full = frozenset(ASSIGNABLE_PANEL_MODULE_KEYS)
    if not panel_auth_enabled():
        return full
    if st.session_state.get("_panel_session_full_access"):
        return full
    if st.session_state.get("_panel_user_role") == "administrador":
        return full
    uid = st.session_state.get("_panel_user_id")
    if uid is None:
        return frozenset()
    cached = st.session_state.get("_panel_module_keys_cache")
    if isinstance(cached, list):
        return frozenset(str(x) for x in cached if str(x) in full)
    ok, code, data = api_client.get_panel_user_effective_modules(int(uid))
    if not ok or not isinstance(data, list):
        return frozenset()
    keys = [str(x) for x in data if str(x) in full]
    st.session_state["_panel_module_keys_cache"] = keys
    return frozenset(keys)


def panel_invalidate_module_cache() -> None:
    st.session_state.pop("_panel_module_keys_cache", None)


def _logout_clear_all() -> None:
    st.session_state["_panel_auth_ok"] = False
    st.session_state.pop("_panel_session_full_access", None)
    st.session_state.pop("panel_mod_radio", None)
    st.session_state.pop("_panel_module_transition", None)
    st.session_state.pop("_panel_just_switched_module", None)
    _clear_db_panel_identity()


def _init_session() -> None:
    if "_panel_auth_ok" not in st.session_state:
        st.session_state["_panel_auth_ok"] = False


def _http_detail(payload: Any) -> str:
    if isinstance(payload, dict):
        d = payload.get("detail")
        if d is not None:
            return str(d)
        return str(payload)
    return str(payload)


def render_login_gate() -> bool:
    """
    Si la autenticación está desactivada, devuelve True de inmediato.
    Si está activa y la sesión es válida, devuelve True.
    En caso contrario muestra el formulario adecuado y detiene el script hasta autenticarse.
    """
    _init_session()
    if not panel_auth_enabled():
        return True

    if st.session_state.get("_panel_auth_ok"):
        return True

    use_db = panel_auth_users_from_database()

    if not use_db:
        cred = _credentials_ok()
        if cred is None:
            st.error(
                "Autenticación del panel activada (`PANEL_AUTH_ENABLED`) pero faltan "
                "**PANEL_LOGIN_USER** o **PANEL_LOGIN_PASSWORD** en `.env`. "
                "Configúralas, o usa `PANEL_AUTH_USERS_SOURCE=database` con tabla `panel_users`."
            )
            st.stop()

        user_env, pass_env = cred
        st.markdown('<p class="neon-title" style="margin-top:1rem;">Acceso al panel</p>', unsafe_allow_html=True)
        st.caption("Credenciales definidas en el entorno (`.env`).")

        _nc1, col, _nc2 = st.columns([1, 1.2, 1])
        with col:
            u_input = st.text_input("Usuario", key="_panel_login_user", autocomplete="username")
            p_input = st.text_input("Contraseña", type="password", key="_panel_login_pass", autocomplete="current-password")
            go = st.button("Entrar", use_container_width=True, type="primary")

        if go:
            ok_u = _safe_str_eq(u_input.strip(), user_env)
            ok_p = _safe_str_eq(p_input, pass_env)
            if ok_u and ok_p:
                st.session_state["_panel_auth_ok"] = True
                _set_env_operator_session()
                st.session_state["_panel_warm_after_login"] = True
                st.rerun()
            else:
                st.markdown(
                    '<div class="m-error"><strong>No se pudo iniciar sesión.</strong> '
                    "Revisa usuario y contraseña.</div>",
                    unsafe_allow_html=True,
                )

        st.stop()

    # --- Modo base de datos ---
    st.markdown('<p class="neon-title" style="margin-top:1rem;">Acceso al panel</p>', unsafe_allow_html=True)

    tab_in, tab_reg = st.tabs(["Iniciar sesión", "Crear cuenta"])

    with tab_in:
        _nc1, col, _nc2 = st.columns([1, 1.2, 1])
        with col:
            u_in = st.text_input("Usuario", key="_panel_db_login_user", autocomplete="username")
            p_in = st.text_input("Contraseña", type="password", key="_panel_db_login_pass", autocomplete="current-password")
            go_in = st.button("Entrar", use_container_width=True, type="primary", key="_panel_db_login_btn")

        if go_in:
            u_norm = u_in.strip().lower()
            if not u_norm or not p_in:
                st.warning("Indica **usuario** y **contraseña**.")
            else:
                ok, code, raw = api_client.post_panel_user_login(u_norm, p_in)
                if ok:
                    user_obj = raw.get("user") if isinstance(raw, dict) else None
                    if isinstance(user_obj, dict) and user_obj.get("id") is not None:
                        _set_db_operator_session(user_obj)
                    else:
                        st.session_state["_panel_session_full_access"] = False
                        _clear_db_panel_identity()
                    st.session_state["_panel_auth_ok"] = True
                    st.session_state["_panel_warm_after_login"] = True
                    st.rerun()
                else:
                    msg = (
                        "No hay conexión con la API. Arranca Litestar y revisa `API_BASE_URL` en `.env`."
                        if code == 0
                        else _http_detail(raw)
                    )
                    st.markdown(
                        '<div class="m-error"><strong>No se pudo iniciar sesión.</strong> '
                        f"{msg}"
                        f"{' (HTTP ' + str(code) + ')' if code else ''}</div>",
                        unsafe_allow_html=True,
                    )

    with tab_reg:
        _nc1, col, _nc2 = st.columns([1, 1.2, 1])
        with col:
            u_r = st.text_input("Usuario", key="_panel_reg_user", autocomplete="username")
            p_r = st.text_input("Contraseña", type="password", key="_panel_reg_pass", autocomplete="new-password")
            p2_r = st.text_input("Repetir contraseña", type="password", key="_panel_reg_pass2", autocomplete="new-password")
            with st.expander("Datos de perfil (opcional)"):
                reg_fn = st.text_input("Nombre", key="_panel_reg_fn")
                reg_ln = st.text_input("Apellido", key="_panel_reg_ln")
                reg_addr = st.text_input("Dirección", key="_panel_reg_addr")
                reg_phone = st.text_input("Celular", key="_panel_reg_phone")
                reg_store = st.selectbox(
                    "Tienda",
                    options=list(PANEL_STORE_CHOICES),
                    format_func=lambda x: PANEL_STORE_LABEL_ES[str(x)],
                    key="_panel_reg_store",
                )
                reg_role = st.selectbox(
                    "Rol",
                    options=list(PANEL_ROLE_CHOICES),
                    format_func=lambda x: PANEL_ROLE_LABEL_ES[str(x)],
                    key="_panel_reg_role",
                )
            go_reg = st.button("Registrarme", use_container_width=True, key="_panel_reg_btn")

        if go_reg:
            if p_r != p2_r:
                st.error("Las contraseñas no coinciden.")
            else:
                ok, code, raw = api_client.post_panel_user_register(
                    u_r.strip().lower(),
                    p_r,
                    first_name=(reg_fn or "").strip(),
                    last_name=(reg_ln or "").strip(),
                    address=(reg_addr or "").strip() or None,
                    phone=(reg_phone or "").strip() or None,
                    store=reg_store,
                    role=reg_role,
                )
                if ok:
                    st.success("Cuenta creada. Puedes iniciar sesión en la pestaña **Iniciar sesión**.")
                elif code == 409:
                    st.error(_http_detail(raw))
                elif code == 422:
                    st.error(f"Datos no válidos: {_http_detail(raw)}")
                else:
                    st.error(
                        f"No se pudo registrar: {_http_detail(raw)}"
                        + (f" (HTTP {code})" if code else "")
                    )

    st.stop()


def panel_logout_button() -> None:
    """Botón en la barra lateral: solo tiene efecto si el login del panel está activo."""
    if not panel_auth_enabled() or not st.session_state.get("_panel_auth_ok"):
        return
    if st.button("Cerrar sesión", use_container_width=True, key="_panel_logout_btn"):
        _logout_clear_all()
        st.rerun()
