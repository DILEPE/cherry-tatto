"""
Panel Streamlit para la API (Litestar): citas, contratos, plantillas y encuestas.

Ejecutar desde la raíz del repositorio (con el mismo Python/venv del proyecto):
  python -m streamlit run streamlit_app/main.py

Si `streamlit` no se reconoce como comando, usa siempre la forma `python -m streamlit`
(o instala dependencias: pip install -r requirements.txt dentro del venv activado).

Logo: coloca `branding.png` en `streamlit_app/assets/` o en `assets/` del proyecto.
Si no hay branding, se usa `app/assets/receipt_rock_city_icon.png` en la barra lateral.
Favicon del navegador: `app/assets/receipt_rock_city_icon_180.png` (generado con
`python scripts/build_receipt_rock_city_logo.py`).
Marca de agua opcional (fondo tipo relieve): `rock_city_watermark.png` en las mismas rutas.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Permite `from streamlit_app import ...` al ejecutar con Streamlit
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")

from collections.abc import Callable
import base64
import html

import streamlit as st

from streamlit_app import api_client
from streamlit_app.citas_tab import render_citas_tab, render_reporte_citas_tab
from streamlit_app.contract_read_view import render_contract_read_view
from streamlit_app.contract_signing import render_contract_express_piercing_view, render_contract_signing_view
from streamlit_app.contracts_admin import render_contract_admin_tab
from streamlit_app.customers_management import render_customers_management_tab
from streamlit_app.panel_auth import (
    ensure_panel_session_initialized,
    panel_allowed_module_keys,
    panel_auth_enabled,
    panel_auth_users_from_database,
    panel_is_operator_admin,
    panel_logout_button,
    render_login_gate,
)
from streamlit_app.panel_users_admin import render_panel_users_tab
from streamlit_app.survey_questions_admin import render_survey_questions_tab

LOGO_CANDIDATES = [
    Path(__file__).resolve().parent / "assets" / "branding.png",
    Path(__file__).resolve().parent.parent / "assets" / "branding.png",
    Path(__file__).resolve().parent.parent / "app" / "assets" / "receipt_rock_city_icon.png",
    Path(__file__).resolve().parent / "assets" / "receipt_rock_city_icon.png",
]

PAGE_ICON_CANDIDATES = [
    Path(__file__).resolve().parent.parent / "app" / "assets" / "receipt_rock_city_icon_180.png",
    Path(__file__).resolve().parent / "assets" / "receipt_rock_city_icon_180.png",
    Path(__file__).resolve().parent.parent / "app" / "assets" / "receipt_rock_city_icon.png",
]

_WATERMARK_CANDIDATES = [
    Path(__file__).resolve().parent / "assets" / "rock_city_watermark.png",
    Path(__file__).resolve().parent.parent / "assets" / "rock_city_watermark.png",
]
# (mtime_ns, css_fragment) para regenerar el data URI si se reemplaza el PNG en disco.
_WATERMARK_STYLE_CACHE: tuple[float, str] | None = None


def _inject_background_watermark_css() -> str:
    """CSS del logo Rock City como marca de agua en relieve (data URI). Vacío si no hay archivo."""
    global _WATERMARK_STYLE_CACHE
    wm_path = next((p for p in _WATERMARK_CANDIDATES if p.is_file()), None)
    if wm_path is None:
        return ""
    try:
        mtime = wm_path.stat().st_mtime
    except OSError:
        return ""
    if _WATERMARK_STYLE_CACHE is not None and _WATERMARK_STYLE_CACHE[0] == mtime:
        return _WATERMARK_STYLE_CACHE[1]
    b64 = base64.standard_b64encode(wm_path.read_bytes()).decode("ascii")
    uri = f"url(data:image/png;base64,{b64})"
    css = f"""
          [data-testid="stAppViewContainer"] {{
            position: relative;
          }}
          [data-testid="stAppViewContainer"]::before {{
            content: "";
            position: fixed;
            inset: 0;
            z-index: 0;
            pointer-events: none;
            background-image: {uri};
            background-repeat: no-repeat;
            background-position: center center;
            background-size: clamp(420px, 88vmin, min(96vw, 1280px));
            opacity: 0.09;
            filter:
              drop-shadow(2px 2px 1px rgba(255,255,255,0.16))
              drop-shadow(-1.5px -1.5px 1px rgba(0,0,0,0.45))
              brightness(1.06)
              contrast(1.08);
            mix-blend-mode: soft-light;
          }}
          [data-testid="stMain"],
          section.main {{
            position: relative;
            z-index: 1 !important;
          }}
    """
    _WATERMARK_STYLE_CACHE = (mtime, css)
    return css


def _inject_material_neon_css() -> None:
    """Se emite en cada rerun: Streamlit reconstruye el DOM y los estilos no persisten entre ejecuciones."""
    wm = _inject_background_watermark_css()
    st.markdown(
        f"""
        <style>
          @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
          html, body, [class*="css"]  {{ font-family: 'Inter', 'Segoe UI', sans-serif !important; }}
          [data-testid="stAppViewContainer"] {{
            background: radial-gradient(ellipse 120% 80% at 50% -20%, rgba(255,0,127,0.075), transparent 55%),
                        radial-gradient(ellipse 80% 50% at 100% 50%, rgba(167,154,255,0.05), transparent 45%),
                        linear-gradient(180deg, #43434e 0%, #3c3c48 42%, #363640 100%);
          }}
          [data-testid="stHeader"] {{ background: rgba(54,54,62,0.94) !important; z-index: 11 !important; }}
          /* Streamlit ≥1.50: scroll en stSidebarUserContent; overflow en el section exterior rompe el layout. */
          [data-testid="stSidebar"],
          section.stSidebar {{
            background: linear-gradient(180deg, #383842 0%, #303038 100%) !important;
            border-right: 1px solid rgba(255,255,255,0.11);
            overflow: visible !important;
          }}
          [data-testid="stSidebarContent"] {{
            display: flex !important;
            flex-direction: column !important;
            min-height: 0 !important;
            height: 100% !important;
            max-height: 100vh !important;
            overflow: hidden !important;
          }}
          [data-testid="stSidebarUserContent"] {{
            flex: 1 1 auto !important;
            min-height: 0 !important;
            overflow-y: auto !important;
            overflow-x: hidden !important;
            overscroll-behavior: contain;
            -webkit-overflow-scrolling: touch;
          }}
          div[data-baseweb="tab-highlight"] {{ background-color: #FF007F !important; box-shadow: 0 0 12px rgba(255,0,127,0.45); }}
          [data-baseweb="tab"] {{ color: #e0e0e0 !important; font-weight: 600; }}
          [data-baseweb="tab"]:hover {{ color: #FF007F !important; }}
          [data-testid="stExpander"] {{
            background: #484854 !important;
            border: 1px solid rgba(255,255,255,0.15) !important;
            border-radius: 12px !important;
            box-shadow: 0 2px 8px rgba(0,0,0,0.38);
          }}
          .neon-title {{
            color: #fff;
            font-weight: 700;
            font-size: 1.35rem;
            letter-spacing: 0.02em;
            text-shadow: 0 0 18px rgba(255,0,127,0.35);
          }}
          .sub-lavender {{ color: #A79AFF; font-weight: 600; font-size: 0.95rem; }}
          .m-error {{
            background: rgba(207,102,121,0.15);
            border: 1px solid #CF6679;
            color: #FFB4A9;
            border-radius: 8px;
            padding: 0.75rem 1rem;
            margin: 0.5rem 0 1rem 0;
            font-size: 0.9rem;
          }}
          .m-success {{
            background: rgba(105,240,174,0.12);
            border: 1px solid #69F0AE;
            color: #B9F6CA;
            border-radius: 8px;
            padding: 0.75rem 1rem;
            margin: 0.5rem 0 1rem 0;
          }}
          div.stButton > button:first-child {{
            border-radius: 999px !important;
            font-weight: 600 !important;
            border: 1px solid rgba(255,0,127,0.55) !important;
            box-shadow: 0 0 16px rgba(255,0,127,0.25) !important;
          }}
          div.stButton > button[kind="secondary"] {{
            border-color: rgba(167,154,255,0.5) !important;
            box-shadow: 0 0 12px rgba(167,154,255,0.2) !important;
          }}
          hr {{ border-color: rgba(255,255,255,0.1) !important; }}
          [data-testid="stTextInput"] input,
          [data-testid="stNumberInput"] input,
          [data-testid="stTextArea"] textarea,
          [data-testid="stSelectbox"] div[data-baseweb="select"] > div {{
            background-color: #50505c !important;
            color: #f2f2f2 !important;
            border-color: rgba(255,255,255,0.22) !important;
          }}
          {wm}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_module_transition_curtain(module_label: str) -> None:
    """Pantalla intermedia de un rerun para enmascarar el montaje del nuevo módulo."""
    safe = html.escape(module_label)
    st.markdown(
        f"""
        <style>
        @keyframes panel-shimmer {{
          0% {{ background-position: 0% 50%; }}
          100% {{ background-position: 200% 50%; }}
        }}
        .panel-transition-curtain {{
          min-height: calc(100vh - 9rem);
          display: flex;
          align-items: center;
          justify-content: center;
          background: linear-gradient(165deg, #42424e 0%, #3c3c46 45%, #363640 100%);
          border-radius: 16px;
          border: 1px solid rgba(255,0,127,0.22);
          box-shadow: inset 0 1px 0 rgba(255,255,255,0.06);
        }}
        .panel-transition-curtain-inner {{
          text-align: center;
          padding: 2rem 2.5rem;
          color: #ececec;
        }}
        .panel-transition-title {{
          font-size: 1.15rem;
          font-weight: 700;
          letter-spacing: 0.03em;
          margin-bottom: 0.35rem;
        }}
        .panel-transition-sub {{
          font-size: 0.92rem;
          opacity: 0.78;
        }}
        .panel-transition-bar {{
          margin: 1.25rem auto 0;
          width: min(280px, 70vw);
          height: 3px;
          border-radius: 999px;
          background: linear-gradient(90deg, transparent, #ff007f, #a79aff, transparent);
          background-size: 200% 100%;
          animation: panel-shimmer 1.15s ease infinite;
        }}
        </style>
        <div class="panel-transition-curtain">
          <div class="panel-transition-curtain-inner">
            <div class="panel-transition-title">{safe}</div>
            <div class="panel-transition-sub">Preparando la vista…</div>
            <div class="panel-transition-bar"></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _logo_path() -> Path | None:
    for p in LOGO_CANDIDATES:
        if p.is_file():
            return p
    return None


def _page_icon() -> str:
    """Emoji por defecto o ruta a PNG/ICO para la pestaña del navegador."""
    for p in PAGE_ICON_CANDIDATES:
        if p.is_file():
            return str(p.resolve())
    return "🍒"


def _api_error(payload) -> str:
    if isinstance(payload, dict):
        return str(payload.get("detail", payload))
    return str(payload)


def main() -> None:
    st.set_page_config(
        page_title="Cherry Ink · Rock City — Panel API",
        page_icon=_page_icon(),
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _inject_material_neon_css()
    ensure_panel_session_initialized()

    render_login_gate()

    pending_panel_toast = st.session_state.pop("_panel_pending_toast", None)
    if pending_panel_toast:
        try:
            st.toast(str(pending_panel_toast), icon="✅")
        except Exception:
            pass

    if st.session_state.pop("_panel_warm_after_login", False):
        with st.spinner("Cargando permisos, profesionales y citas…"):
            _warm_mods = panel_allowed_module_keys()
            from streamlit_app.cached_public_api import get_panel_users_assignable_cached

            get_panel_users_assignable_cached()
            from streamlit_app.citas_tab import warm_session_after_login

            warm_session_after_login(_warm_mods)

    # Rutas internas del mismo panel (query_params), no enlaces públicos anónimos:
    # requieren sesión del panel (gate anterior). Navegar con botones (panel_navigation), no link_button.
    view = st.query_params.get("view")
    if view == "contract_sign":
        express_raw = (st.query_params.get("express_piercing") or "").strip().lower()
        if express_raw in ("1", "true", "yes", "on"):
            render_contract_express_piercing_view()
            return
        appt_id_raw = st.query_params.get("appointment_id")
        try:
            appt_id = int(appt_id_raw) if appt_id_raw is not None else 0
        except ValueError:
            appt_id = 0
        if appt_id <= 0:
            st.error("URL inválida: falta appointment_id.")
        else:
            render_contract_signing_view(appt_id)
        return
    if view == "contract_read":
        contract_id_raw = st.query_params.get("contract_id")
        try:
            contract_id = int(contract_id_raw) if contract_id_raw is not None else 0
        except ValueError:
            contract_id = 0
        if contract_id <= 0:
            st.error("URL inválida: falta contract_id.")
        else:
            render_contract_read_view(contract_id)
        return

    allowed_modules = panel_allowed_module_keys()
    if (
        panel_auth_enabled()
        and panel_auth_users_from_database()
        and not panel_is_operator_admin()
        and len(allowed_modules) == 0
    ):
        st.markdown('<p class="neon-title">Panel de operaciones</p>', unsafe_allow_html=True)
        st.warning(
            "Tu usuario no tiene ningún módulo del panel asignado. "
            "Pide a un **administrador** que marque los módulos en **Gestión de usuarios → Editar → Módulos permitidos**."
        )
        st.stop()

    module_definitions: list[tuple[str, str, Callable[[], None]]] = []
    if "citas" in allowed_modules:
        module_definitions.append(("citas", "Gestión citas", render_citas_tab))
    if "clientes" in allowed_modules:
        module_definitions.append(("clientes", "Gestión de clientes", render_customers_management_tab))
    if "contratos" in allowed_modules:
        module_definitions.append(("contratos", "Gestión contratos", render_contract_admin_tab))
    if "encuestas" in allowed_modules:
        module_definitions.append(("encuestas", "Gestión encuesta", render_survey_questions_tab))
    if panel_is_operator_admin():
        module_definitions.append(("usuarios_panel", "Gestión de usuarios", render_panel_users_tab))
    if "reporte" in allowed_modules:
        module_definitions.append(("reporte", "Reporte", render_reporte_citas_tab))

    if not module_definitions:
        st.error("No hay módulos visibles para tu usuario.")
        st.stop()

    with st.sidebar:
        logo = _logo_path()
        if logo:
            st.image(str(logo), use_container_width=True)
        else:
            st.markdown('<p class="neon-title">CHERRY INK</p>', unsafe_allow_html=True)
            st.markdown('<p class="sub-lavender">Rock City Piercing</p>', unsafe_allow_html=True)
        st.markdown("---")
        if len(module_definitions) == 1:
            active_module_key = module_definitions[0][0]
        else:
            labels = [row[1] for row in module_definitions]
            key_by_label = {row[1]: row[0] for row in module_definitions}
            picked = st.radio("Módulo activo", options=labels, key="panel_mod_radio")
            active_module_key = key_by_label[picked]

        prev_mod = st.session_state.get("_panel_prev_module_key")
        if prev_mod != active_module_key:
            if prev_mod is not None:
                st.session_state["_panel_module_transition"] = True
            st.session_state["_panel_prev_module_key"] = active_module_key
            if prev_mod is not None:
                ap_mods = frozenset({"citas", "reporte"})
                if active_module_key in ap_mods or prev_mod in ap_mods:
                    st.session_state["_ap_reload"] = True
                if active_module_key == "clientes" or prev_mod == "clientes":
                    st.session_state["_cust_reload"] = True

        st.markdown("---")
        if st.button("Probar conexión", use_container_width=True):
            ok, code, data = api_client.get_appointments()
            if ok:
                st.success(f"Conexión OK (HTTP {code})")
            else:
                detail = _api_error(data)
                st.error(f"Sin respuesta correcta (HTTP {code}): {detail}")
                if code == 0 or "10061" in detail or "Max retries" in detail or "Failed to establish" in detail:
                    st.info(
                        "No hay servidor en esa dirección. En **otra terminal** (mismo venv), "
                        "desde la raíz del repo ejecuta: "
                        "`python -m uvicorn app.main:app --host 127.0.0.1 --port 5000` "
                        "y comprueba que el puerto coincida con la URL del panel (variable `PORT` en `.env`)."
                    )

        if st.button("Verificar n8n", use_container_width=True):
            nivel, msg_n8n = api_client.check_n8n_webhook_connection()
            if nivel == "success":
                st.success(msg_n8n)
            elif nivel == "warn":
                st.warning(msg_n8n)
            else:
                st.error(msg_n8n)

        panel_logout_button()

    st.markdown('<p class="neon-title">Panel de operaciones</p>', unsafe_allow_html=True)

    if st.session_state.pop("_panel_module_transition", False):
        _transition_label = next(
            (lb for k, lb, _ in module_definitions if k == active_module_key),
            active_module_key,
        )
        _render_module_transition_curtain(_transition_label)
        st.rerun()

    for mod_key, _label, render_fn in module_definitions:
        if mod_key == active_module_key:
            with st.spinner("Cargando módulo…"):
                render_fn()
            break


if __name__ == "__main__":
    main()
