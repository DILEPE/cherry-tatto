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
import json
import os
import time
from pathlib import Path
from typing import Any, Final

import streamlit as st
import streamlit.components.v1 as components

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

# Se ejecuta dentro del iframe/documento principal de Streamlit (inyectado con <script>).
_LOGIN_AUTOFILL_INNER_JS = r"""
(function () {
  var NS = "__panelLoginAutofillSync_v5";
  if (window[NS]) return;
  window[NS] = true;

  function loginColumn() {
    return document.querySelector('section.main [data-testid="column"]:has(.panel-login-frame-root)');
  }

  function visitNode(node, fnInp) {
    if (!node) return;
    if (node.nodeType === 1 && node.tagName === "INPUT") {
      var t = String(node.type || "").toLowerCase();
      if (t === "text" || t === "password" || t === "email") fnInp(node);
    }
    if (node.shadowRoot) visitNode(node.shadowRoot, fnInp);
    var ch = node.children;
    if (!ch) return;
    for (var i = 0; i < ch.length; i++) visitNode(ch[i], fnInp);
  }

  function eachLoginInput(fn) {
    var col = loginColumn();
    var scope = col || document.querySelector("section.main") || document.body;
    visitNode(scope, fn);
  }

  function wakeInput(inp) {
    var v = inp.value;
    if (v === undefined || v === null) v = "";
    try {
      var desc = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value");
      if (desc && desc.set) desc.set.call(inp, v);
    } catch (e1) {}
    try {
      var tr = inp._valueTracker;
      if (tr && typeof tr.setValue === "function") tr.setValue("");
    } catch (e2) {}
    try {
      inp.dispatchEvent(new InputEvent("input", { bubbles: true, cancelable: true }));
    } catch (e3) {
      try { inp.dispatchEvent(new Event("input", { bubbles: true })); } catch (e4) {}
    }
    try { inp.dispatchEvent(new Event("change", { bubbles: true })); } catch (e5) {}
  }

  function wakeAll() {
    eachLoginInput(wakeInput);
  }

  function burstWake() {
    wakeAll();
    try {
      queueMicrotask(wakeAll);
    } catch (e0) {}
    try {
      requestAnimationFrame(function () {
        wakeAll();
        requestAnimationFrame(wakeAll);
      });
    } catch (e1) {}
  }

  function bindAutofillHooks() {
    eachLoginInput(function (inp) {
      if (inp.dataset.panelLoginAutofillHook) return;
      inp.dataset.panelLoginAutofillHook = "1";
      inp.addEventListener("animationstart", function (ev) {
        if (ev && ev.animationName && ev.animationName.indexOf("panel-login-autofill-start") !== -1) {
          wakeInput(inp);
        }
      });
    });
  }

  function bindPreInteractWake() {
    var col = loginColumn();
    if (!col || col.dataset.panelLoginInteractWake) return;
    col.dataset.panelLoginInteractWake = "1";
    ["mousedown", "touchstart", "pointerdown", "click"].forEach(function (etype) {
      col.addEventListener(
        etype,
        function () {
          burstWake();
        },
        true
      );
    });
  }

  function bindDocCaptureWake() {
    if (document.documentElement.dataset.panelLoginDocWake) return;
    document.documentElement.dataset.panelLoginDocWake = "1";
    ["pointerdown", "mousedown", "touchstart"].forEach(function (etype) {
      document.addEventListener(etype, burstWake, true);
    });
  }

  function bindFocusSync() {
    if (document.documentElement.dataset.panelLoginFocusinWake) return;
    document.documentElement.dataset.panelLoginFocusinWake = "1";
    document.addEventListener(
      "focusin",
      function (ev) {
        var t = ev.target;
        if (!t || String(t.tagName || "").toUpperCase() !== "INPUT") return;
        var col = loginColumn();
        if (col && col.contains(t)) wakeInput(t);
      },
      true
    );
  }

  function run() {
    bindAutofillHooks();
    bindPreInteractWake();
    bindDocCaptureWake();
    bindFocusSync();
    burstWake();
  }

  run();
  setTimeout(run, 0);
  setTimeout(run, 40);
  setTimeout(run, 120);
  setTimeout(run, 400);
  setTimeout(run, 1000);
  setTimeout(run, 2200);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) setTimeout(run, 40);
  });
})();
"""


def _login_autofill_component_html() -> str:
    inner_lit = json.dumps(_LOGIN_AUTOFILL_INNER_JS)
    return f"""<script>
(function () {{
  function appDocument() {{
    try {{
      var t = window.top;
      if (t && t.document && t.document.querySelector('[data-testid="stApp"]')) return t.document;
    }} catch (e0) {{}}
    var x = window;
    for (var i = 0; i < 12; i++) {{
      try {{
        if (!x || !x.document) break;
        var d = x.document;
        if (d.querySelector('[data-testid="stApp"]')) return d;
        if (x.parent === x) break;
        x = x.parent;
      }} catch (e) {{
        break;
      }}
    }}
    try {{
      return window.top.document;
    }} catch (e2) {{
      return document;
    }}
  }}
  function injectScript(doc, text) {{
    try {{
      var s = doc.createElement("script");
      s.textContent = text;
      (doc.head || doc.documentElement).appendChild(s);
      s.remove();
    }} catch (e) {{}}
  }}
  injectScript(appDocument(), {inner_lit});
}})();
</script>"""


def _inject_login_autofill_sync_script() -> None:
    """Sincroniza autofill del navegador con React/Streamlit (script en el documento de la app)."""
    components.html(_login_autofill_component_html(), height=0, width=0)


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
    for _lk in (
        "_panel_login_user",
        "_panel_login_pass",
        "_panel_db_login_user",
        "_panel_db_login_pass",
    ):
        st.session_state.pop(_lk, None)
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
            padding: 1.5rem 1.35rem 1.75rem !important;
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
             usuario/contraseña quedan por debajo de la cortina en el apilamiento.
             Cuando la cortina está subida (--locked-open), el shell se colapsa para no solapar.
             Los inputs llevan pointer-events explícitos por si queda algún contenedor que los bloquee. */
          section.main [data-testid="column"]:has(.panel-login-frame-root) div:has(> .panel-login-gate-shell) {
            position: relative;
            z-index: 40 !important;
          }
          section.main [data-testid="column"]:has(.panel-login-frame-root) [data-testid="stTextInput"],
          section.main [data-testid="column"]:has(.panel-login-frame-root) [data-testid="stTextInputRootElement"],
          section.main [data-testid="column"]:has(.panel-login-frame-root) .stTextInput {
            position: relative;
            z-index: 80 !important;
            pointer-events: auto !important;
          }
          section.main [data-testid="column"]:has(.panel-login-frame-root) [data-testid="stTextInput"] input {
            pointer-events: auto !important;
          }
          section.main [data-testid="column"]:has(.panel-login-frame-root) [data-testid="baseButton-primary"],
          section.main [data-testid="column"]:has(.panel-login-frame-root) [data-testid="stTabs"] [data-testid="baseButton"] {
            position: relative;
            z-index: 80 !important;
            pointer-events: auto !important;
          }
          section.main [data-testid="column"]:has(.panel-login-frame-root) [data-testid="stSelectbox"],
          section.main [data-testid="column"]:has(.panel-login-frame-root) [data-testid="stExpander"] {
            position: relative;
            z-index: 80 !important;
            pointer-events: auto !important;
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
          /* Tras subir la cortina ya no debe quedar capa invisible sobre usuario/contraseña */
          .panel-login-gate-shell:has(.panel-login-gate-curtain--locked-open) {
            height: 0 !important;
            min-height: 0 !important;
            margin-bottom: 0 !important;
            padding: 0 !important;
            overflow: hidden !important;
            pointer-events: none !important;
            border: none !important;
            box-shadow: none !important;
          }
          /* Solo el power controla la cortina (sin hover). */
          /* Registro: más alto para cubrir más campos antes de subir la cortina */
          .panel-login-gate-shell.panel-login-gate-shell--tall {
            height: 540px;
            margin-bottom: -540px;
          }
          /* Chrome/Edge: autofill no notifica a React; animación mínima para enganchar animationstart */
          @keyframes panel-login-autofill-start {
            from { opacity: 0.999; }
            to { opacity: 1; }
          }
          section.main [data-testid="column"]:has(.panel-login-frame-root) input:-webkit-autofill {
            animation-name: panel-login-autofill-start;
            animation-duration: 0.001s;
          }
          /* Campos más compactos y centrados en la tarjeta */
          section.main [data-testid="column"]:has(.panel-login-frame-root) [data-testid="stTextInput"] {
            max-width: 320px;
            margin-left: auto !important;
            margin-right: auto !important;
          }
          section.main [data-testid="column"]:has(.panel-login-frame-root) [data-testid="stTextInput"] input {
            min-height: 2.35rem;
            font-size: 0.95rem;
          }
          section.main [data-testid="column"]:has(.panel-login-frame-root) [data-testid="stForm"] {
            max-width: 320px;
            margin-left: auto;
            margin-right: auto;
          }
          section.main [data-testid="column"]:has(.panel-login-frame-root) [data-testid="stFormSubmitButton"] {
            width: 100%;
            max-width: 320px;
            margin-left: auto !important;
            margin-right: auto !important;
            display: flex;
            justify-content: center;
          }
          section.main [data-testid="column"]:has(.panel-login-frame-root) [data-testid="stFormSubmitButton"] button {
            width: 100%;
            max-width: 320px;
            min-height: 2.45rem;
            font-size: 0.95rem;
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
        _, mid, _ = st.columns([1.25, 2.15, 1.25])
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
                # st.form: al enviar, Streamlit serializa los widgets del bloque junto (mejor con autofill).
                with st.form("panel_env_login_form", clear_on_submit=False):
                    # Rellenar desde .env en session_state **antes** del widget: así «Entrar» lee
                    # valores válidos sin tener que hacer clic en los inputs primero.
                    if "_panel_login_user" not in st.session_state:
                        st.session_state["_panel_login_user"] = user_env
                    if "_panel_login_pass" not in st.session_state:
                        st.session_state["_panel_login_pass"] = pass_env
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
                    go = st.form_submit_button("Entrar", use_container_width=True, type="primary")

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

                _inject_login_autofill_sync_script()

        st.stop()

    # --- Modo base de datos ---
    _, mid, _ = st.columns([1.25, 2.15, 1.25])
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
                with st.form("panel_db_login_form", clear_on_submit=False):
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
                    go_in = st.form_submit_button("Entrar", use_container_width=True, type="primary")

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

        if co and _panel_login_curtain_fields_ready():
            _inject_login_autofill_sync_script()

    st.stop()


def panel_logout_button() -> None:
    """Botón en la barra lateral: solo tiene efecto si el login del panel está activo."""
    if not panel_auth_enabled() or not st.session_state.get("_panel_auth_ok"):
        return
    if st.button("Cerrar sesión", use_container_width=True, key="_panel_logout_btn"):
        _logout_clear_all()
        st.rerun()
