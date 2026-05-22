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
import html

import streamlit as st

from streamlit_app import api_client
from streamlit_app.citas_tab import render_citas_tab
from streamlit_app.reporte_tab import render_reporte_citas_tab
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
    render_login_gate,
)
from streamlit_app.panel_users_admin import render_panel_users_tab
from streamlit_app.stores_management import render_stores_management_tab
from streamlit_app.survey_questions_admin import render_survey_questions_tab
from streamlit_app.panel_sidebar import render_panel_sidebar
from streamlit_app.theme import inject_panel_theme, render_theme_mode_control

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

def _render_module_transition_curtain(module_label: str) -> None:
    """Pantalla intermedia de un rerun para enmascarar el montaje del nuevo módulo."""
    safe = html.escape(module_label)
    st.markdown(
        f"""
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


def main() -> None:
    st.set_page_config(
        page_title="Cherry Ink · Rock City — Panel API",
        page_icon=_page_icon(),
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_panel_theme(st)
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
        module_definitions.append(("tiendas", "Gestión de tiendas", render_stores_management_tab))
        module_definitions.append(("usuarios_panel", "Gestión de usuarios", render_panel_users_tab))
    if "reporte" in allowed_modules:
        module_definitions.append(("reporte", "Gestión reportes", render_reporte_citas_tab))

    if not module_definitions:
        st.error("No hay módulos visibles para tu usuario.")
        st.stop()

    # Después de login siempre arrancar en citas (o primer módulo disponible).
    # Seteamos explícitamente para sobreescribir el valor que Streamlit puede restaurar
    # del frontend aunque la clave no esté en session_state.
    if st.session_state.pop("_panel_reset_to_citas", False):
        _citas_label = next((ml for mk, ml, _ in module_definitions if mk == "citas"), None)
        _reset_label = _citas_label or module_definitions[0][1]
        st.session_state["panel_mod_radio"] = _reset_label
        st.session_state.pop("_panel_prev_module_key", None)

    with st.sidebar:
        active_module_key = render_panel_sidebar(module_definitions, _logo_path())

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
