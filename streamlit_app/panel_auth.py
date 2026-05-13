"""
Autenticación del panel Streamlit.

- Modo **env** (`PANEL_AUTH_USERS_SOURCE=env` o sin definir): usuario/contraseña en `.env`.
- Modo **database**: usuarios en MySQL (`panel_users`), registro e inicio de sesión vía API.

Las rutas `?view=contract_sign` y `?view=contract_read` son vistas del mismo panel; tras iniciar sesión
se resuelven en `main()` y también exigen esta autenticación (no son enlaces anónimos).
"""
from __future__ import annotations

import base64
import hmac
import os
import time
from pathlib import Path
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
"""Segundos: debe ser ≥ duración CSS de la cortina (0.52s) para no crear widgets antes."""
_PANEL_CURTAIN_ANIM_DONE_S: Final[float] = 0.58


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


def _pop_login_curtain_ui_state() -> None:
    st.session_state.pop("_panel_login_curtain_open", None)
    st.session_state.pop("_panel_login_curtain_started_at", None)
    st.session_state.pop("_panel_login_fields_ready", None)


def _logout_clear_all() -> None:
    st.session_state["_panel_auth_ok"] = False
    st.session_state.pop("_panel_session_full_access", None)
    st.session_state.pop("panel_mod_radio", None)
    st.session_state.pop("_panel_module_transition", None)
    st.session_state.pop("_panel_just_switched_module", None)
    _pop_login_curtain_ui_state()
    _clear_db_panel_identity()


def _init_session() -> None:
    if "_panel_auth_ok" not in st.session_state:
        st.session_state["_panel_auth_ok"] = False


def _ensure_login_curtain_session_defaults() -> None:
    """Solo el botón power controla si la cortina está arriba y los campos son visibles."""
    if "_panel_login_curtain_open" not in st.session_state:
        st.session_state["_panel_login_curtain_open"] = False


def _panel_login_curtain_fields_ready() -> bool:
    """Los widgets solo existen tras la animación (CSS no oculta bien los iframes de Streamlit)."""
    return bool(st.session_state.get("_panel_login_fields_ready"))


@st.fragment(run_every=0.12)
def _panel_login_curtain_poll_fragment() -> None:
    """Hasta que pase la animación no se crean inputs; este fragmento fuerza reruns cortos solo ese tiempo."""
    if not st.session_state.get("_panel_login_curtain_open"):
        return
    if st.session_state.get("_panel_login_fields_ready"):
        return
    t0 = st.session_state.get("_panel_login_curtain_started_at")
    if t0 is None:
        st.session_state["_panel_login_fields_ready"] = True
        st.rerun()
        return
    if (time.monotonic() - float(t0)) >= _PANEL_CURTAIN_ANIM_DONE_S:
        st.session_state["_panel_login_fields_ready"] = True
        st.rerun()


def _render_login_curtain_power_toggle(*, button_key: str) -> None:
    """Solo el power sube o baja la cortina (logo); los campos no se muestran hasta terminar la animación."""
    on = bool(st.session_state.get("_panel_login_curtain_open"))
    if st.button(
        " ",
        key=button_key,
        help=(
            "Apagar: bajar la cortina y volver a ver el logo."
            if on
            else "Encender: subir la cortina para introducir usuario y contraseña."
        ),
        type="secondary",
        icon=":material/power_settings_new:" if not on else ":material/power_off:",
        width="content",
    ):
        new_on = not on
        st.session_state["_panel_login_curtain_open"] = new_on
        if new_on:
            st.session_state["_panel_login_curtain_started_at"] = time.monotonic()
            st.session_state["_panel_login_fields_ready"] = False
        else:
            st.session_state.pop("_panel_login_curtain_started_at", None)
            st.session_state.pop("_panel_login_fields_ready", None)
        st.rerun()


def ensure_panel_session_initialized() -> None:
    """
    Garantiza que existan las claves por defecto del panel sin borrar un login ya válido.
    Debe llamarse al inicio de `main()` antes de `render_login_gate()`.
    """
    _init_session()


def _http_detail(payload: Any) -> str:
    if isinstance(payload, dict):
        d = payload.get("detail")
        if d is not None:
            return str(d)
        return str(payload)
    return str(payload)


def _panel_branding_png_path() -> Path | None:
    """Misma marca de agua que el fondo del panel (`rock_city_watermark.png`)."""
    for p in (
        Path(__file__).resolve().parent / "assets" / "rock_city_watermark.png",
        Path(__file__).resolve().parent.parent / "assets" / "rock_city_watermark.png",
    ):
        if p.is_file():
            return p
    return None


def _inject_login_brand_styles() -> None:
    """Marco del login: cortina con logo solo controlada por power."""
    st.markdown(
        """
        <style>
          /* Recuadro centrado: columna media que contiene el marcador oculto */
          section.main [data-testid="column"]:has(.panel-login-frame-root) {
            background: linear-gradient(165deg, rgba(44, 44, 52, 0.96), rgba(28, 28, 34, 0.99));
            border: 1px solid rgba(255, 255, 255, 0.14);
            border-radius: 20px;
            padding: 1.75rem 1.55rem 2rem !important;
            box-shadow:
              0 0 0 1px rgba(255, 0, 127, 0.14),
              0 20px 56px rgba(0, 0, 0, 0.55),
              inset 0 1px 0 rgba(255, 255, 255, 0.08);
            margin-top: 0.75rem;
            margin-bottom: 1rem;
            overflow: hidden;
            isolation: isolate;
          }
          /* Streamlit pinta los widgets después del markdown en el mismo bloque: sin esto,
             usuario/contraseña quedan por encima de la cortina y parecen “sobresalir”.
             pointer-events: none en el wrapper y auto solo en la cortina permite clicar los inputs
             cuando la cortina está arriba. */
          section.main [data-testid="column"]:has(.panel-login-frame-root) div:has(> .panel-login-gate-shell) {
            position: relative;
            z-index: 40 !important;
            pointer-events: none;
          }
          section.main [data-testid="column"]:has(.panel-login-frame-root) [data-testid="stTextInput"],
          section.main [data-testid="column"]:has(.panel-login-frame-root) [data-testid="stTextInputRootElement"],
          section.main [data-testid="column"]:has(.panel-login-frame-root) .stTextInput {
            position: relative;
            z-index: 1 !important;
          }
          section.main [data-testid="column"]:has(.panel-login-frame-root) [data-testid="baseButton-primary"],
          section.main [data-testid="column"]:has(.panel-login-frame-root) [data-testid="stTabs"] [data-testid="baseButton"] {
            position: relative;
            z-index: 1 !important;
          }
          section.main [data-testid="column"]:has(.panel-login-frame-root) [data-testid="stSelectbox"],
          section.main [data-testid="column"]:has(.panel-login-frame-root) [data-testid="stExpander"] {
            position: relative;
            z-index: 1 !important;
          }
          /* Hueco que solapa el formulario; logo completo visible (contain) */
          .panel-login-gate-shell {
            position: relative;
            width: 100%;
            height: 432px;
            margin-bottom: -432px;
            z-index: 1;
            overflow: hidden;
            border-radius: 12px;
            pointer-events: none;
          }
          .panel-login-gate-curtain {
            pointer-events: auto;
            position: absolute;
            left: 0;
            right: 0;
            top: 0;
            height: 100%;
            transform: translateY(0);
            transition: transform 0.52s cubic-bezier(0.4, 0, 0.2, 1);
            will-change: transform;
            z-index: 2;
            border: 1px solid rgba(255, 0, 127, 0.35);
            border-radius: 12px;
            box-shadow:
              0 0 0 1px rgba(167, 154, 255, 0.12),
              0 12px 36px rgba(0, 0, 0, 0.45);
            background: linear-gradient(165deg, #2a2a32, #121218);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            overflow: hidden;
            padding: 18px 20px;
          }
          .panel-login-gate-curtain-img {
            display: block;
            position: relative;
            width: auto;
            height: auto;
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
            object-position: center center;
            pointer-events: none;
          }
          .panel-login-gate-curtain--locked-open {
            transform: translateY(-100%) !important;
            pointer-events: none !important;
          }
          /* Solo el power controla la cortina (sin hover). */
          /* Registro: más alto para cubrir más campos antes de subir la cortina */
          .panel-login-gate-shell.panel-login-gate-shell--tall {
            height: 540px;
            margin-bottom: -540px;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_login_frame_open() -> None:
    """Marcador para aplicar el recuadro CSS a la columna centrada."""
    st.markdown(
        '<div class="panel-login-frame-root" aria-hidden="true"></div>',
        unsafe_allow_html=True,
    )


def render_login_gate_door(*, tall_overlap: bool = False, curtain_locked_open: bool = False) -> None:
    """
    Cortina con el logo (solo imagen). Subida o bajada únicamente con el botón power
    (`curtain_locked_open`). Los campos se montan después en Python cuando termina la animación.
    """
    pth = _panel_branding_png_path()
    b64: str | None = None
    if pth is not None:
        try:
            b64 = base64.standard_b64encode(pth.read_bytes()).decode("ascii")
        except OSError:
            b64 = None

    img_block = (
        f'<img class="panel-login-gate-curtain-img" src="data:image/png;base64,{b64}" '
        'alt="" draggable="false" />'
        if b64
        else ""
    )
    shell_class = "panel-login-gate-shell panel-login-gate-shell--tall" if tall_overlap else "panel-login-gate-shell"
    curtain_cls = "panel-login-gate-curtain"
    if curtain_locked_open:
        curtain_cls += " panel-login-gate-curtain--locked-open"
    st.markdown(
        f"""
        <div class="{shell_class}">
          <div class="{curtain_cls}" role="presentation">
            {img_block}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


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

    _inject_login_brand_styles()
    _ensure_login_curtain_session_defaults()

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
        _, mid, _ = st.columns([1, 3.35, 1])
        with mid:
            _render_login_frame_open()
            _pw1, _pw2 = st.columns([6, 1])
            with _pw2:
                _render_login_curtain_power_toggle(button_key="_panel_power_env")
            st.markdown(
                '<p class="neon-title" style="margin-top:0.35rem;text-align:center;">Acceso al panel</p>',
                unsafe_allow_html=True,
            )
            st.caption("Credenciales definidas en el entorno (`.env`).")
            co = bool(st.session_state.get("_panel_login_curtain_open"))
            render_login_gate_door(curtain_locked_open=co)
            if co and not _panel_login_curtain_fields_ready():
                _panel_login_curtain_poll_fragment()
            if co and _panel_login_curtain_fields_ready():
                st.text_input(
                    "Usuario",
                    key="_panel_login_user",
                    autocomplete="username",
                )
                st.text_input(
                    "Contraseña",
                    type="password",
                    key="_panel_login_pass",
                    autocomplete="current-password",
                )
                go = st.button("Entrar", use_container_width=True, type="primary", key="_panel_env_enter_btn")

                if go:
                    u_input = str(st.session_state.get("_panel_login_user") or "")
                    p_input = str(st.session_state.get("_panel_login_pass") or "")
                    ok_u = _safe_str_eq(u_input.strip(), user_env)
                    ok_p = _safe_str_eq(p_input, pass_env)
                    if ok_u and ok_p:
                        st.session_state["_panel_auth_ok"] = True
                        _set_env_operator_session()
                        st.session_state["_panel_warm_after_login"] = True
                        _pop_login_curtain_ui_state()
                        st.rerun()
                    else:
                        st.markdown(
                            '<div class="m-error"><strong>No se pudo iniciar sesión.</strong> '
                            "Revisa usuario y contraseña.</div>",
                            unsafe_allow_html=True,
                        )

        st.stop()

    # --- Modo base de datos ---
    _, mid, _ = st.columns([1, 3.35, 1])
    with mid:
        _render_login_frame_open()
        _pw1, _pw2 = st.columns([6, 1])
        with _pw2:
            _render_login_curtain_power_toggle(button_key="_panel_power_db_main")
        st.markdown(
            '<p class="neon-title" style="margin-top:0.35rem;text-align:center;">Acceso al panel</p>',
            unsafe_allow_html=True,
        )

        co = bool(st.session_state.get("_panel_login_curtain_open"))
        if co and not _panel_login_curtain_fields_ready():
            _panel_login_curtain_poll_fragment()

        tab_in, tab_reg = st.tabs(["Iniciar sesión", "Crear cuenta"])

        with tab_in:
            render_login_gate_door(curtain_locked_open=co)
            if co and _panel_login_curtain_fields_ready():
                st.text_input(
                    "Usuario",
                    key="_panel_db_login_user",
                    autocomplete="username",
                )
                st.text_input(
                    "Contraseña",
                    type="password",
                    key="_panel_db_login_pass",
                    autocomplete="current-password",
                )
                go_in = st.button("Entrar", use_container_width=True, type="primary", key="_panel_db_enter_btn")

                if go_in:
                    u_raw = str(st.session_state.get("_panel_db_login_user") or "").strip()
                    p_in = str(st.session_state.get("_panel_db_login_pass") or "")
                    u_norm = u_raw.lower()
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
                            _pop_login_curtain_ui_state()
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
            render_login_gate_door(
                tall_overlap=True,
                curtain_locked_open=co,
            )
            if co and _panel_login_curtain_fields_ready():
                u_r = st.text_input(
                    "Usuario",
                    key="_panel_reg_user",
                    autocomplete="username",
                )
                p_r = st.text_input(
                    "Contraseña",
                    type="password",
                    key="_panel_reg_pass",
                    autocomplete="new-password",
                )
                p2_r = st.text_input(
                    "Repetir contraseña",
                    type="password",
                    key="_panel_reg_pass2",
                    autocomplete="new-password",
                )
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
