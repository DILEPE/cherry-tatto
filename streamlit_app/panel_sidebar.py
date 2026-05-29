"""Barra lateral: rail de iconos cuando Streamlit contrae el sidebar (botón nativo)."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import streamlit as st

from streamlit_app import api_client
from streamlit_app.panel_auth import panel_auth_enabled, panel_logout_button
from streamlit_app.theme import render_theme_mode_control

_MODULE_ICONS: dict[str, str] = {
    "citas": ":material/event:",
    "clientes": ":material/group:",
    "contratos": ":material/description:",
    "encuestas": ":material/quiz:",
    "tiendas": ":material/store:",
    "usuarios_panel": ":material/manage_accounts:",
    "reporte": ":material/assessment:",
}


def render_sidebar_logo(logo: Path | None) -> None:
    if logo:
        st.image(str(logo), use_container_width=True)
    else:
        st.markdown('<p class="panel-sb-expanded-only neon-title">CHERRY INK</p>', unsafe_allow_html=True)
        st.markdown(
            '<p class="panel-sb-rail-only panel-sidebar-logo-mini">RC</p>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<p class="panel-sb-expanded-only sub-lavender">Rock City Piercing</p>',
            unsafe_allow_html=True,
        )


def _render_module_rail_buttons(
    module_definitions: list[tuple[str, str, Callable[[], None]]],
    *,
    current_key: str,
    label_by_key: dict[str, str],
) -> None:
    with st.container(key="panel_sb_modules_rail"):
        for mod_key, label, _ in module_definitions:
            is_active = mod_key == current_key
            if st.button(
                "",
                icon=_MODULE_ICONS.get(mod_key, ":material/apps:"),
                key=f"_panel_mod_rail_{mod_key}",
                help=label,
                use_container_width=True,
                type="primary" if is_active else "secondary",
                disabled=len(module_definitions) == 1,
            ):
                st.session_state["panel_mod_radio"] = label_by_key[mod_key]
                st.rerun()


def render_sidebar_modules(
    module_definitions: list[tuple[str, str, Callable[[], None]]],
) -> str:
    """Devuelve la clave del módulo activo. Rail + radio conviven; CSS muestra uno u otro."""
    if len(module_definitions) == 1:
        mod_key, label, _ = module_definitions[0]
        _render_module_rail_buttons(
            module_definitions,
            current_key=mod_key,
            label_by_key={mod_key: label},
        )
        return mod_key

    labels = [row[1] for row in module_definitions]
    key_by_label = {row[1]: row[0] for row in module_definitions}
    label_by_key = {row[0]: row[1] for row in module_definitions}

    current_label = str(st.session_state.get("panel_mod_radio") or labels[0])
    if current_label not in key_by_label:
        current_label = labels[0]
        st.session_state["panel_mod_radio"] = current_label
    current_key = key_by_label[current_label]

    _render_module_rail_buttons(
        module_definitions,
        current_key=current_key,
        label_by_key=label_by_key,
    )

    picked = st.radio("Módulo activo", options=labels, key="panel_mod_radio")
    return key_by_label[picked]


def _api_error(payload: Any) -> str:
    if isinstance(payload, dict):
        return str(payload.get("detail", payload))
    return str(payload)


def render_sidebar_toolbar() -> None:
    """Iconos de utilidad apilados (mismo ancho que módulos en rail)."""
    show_logout = panel_auth_enabled() and st.session_state.get("_panel_auth_ok")

    with st.container(key="panel_sb_toolbar"):
        if st.button(
            "",
            icon=":material/cloud_sync:",
            use_container_width=True,
            key="_sidebar_test_api",
            help="Probar conexión",
        ):
            ok, code, data = api_client.get_appointments()
            if ok:
                st.toast(f"Conexión OK (HTTP {code})", icon="✅")
            else:
                detail = _api_error(data)
                msg = f"Sin respuesta correcta (HTTP {code}): {detail}"
                if code == 0 or "10061" in detail or "Max retries" in detail or "Failed to establish" in detail:
                    msg += (
                        " — No hay servidor en esa dirección. Arranca la API: "
                        "`python -m uvicorn app.main:app --host 127.0.0.1 --port 5000` "
                        "(puerto según `PORT` en `.env`)."
                    )
                st.toast(msg, icon="❌", duration="long")

        if st.button(
            "",
            icon=":material/hub:",
            use_container_width=True,
            key="_sidebar_check_n8n",
            help="Verificar n8n",
        ):
            nivel, msg_n8n = api_client.check_n8n_webhook_connection()
            if nivel == "success":
                st.toast(msg_n8n, icon="✅")
            elif nivel == "warn":
                st.toast(msg_n8n, icon="⚠️", duration="long")
            else:
                st.toast(msg_n8n, icon="❌", duration="long")

        if show_logout:
            panel_logout_button(compact=True)


def render_panel_sidebar(
    module_definitions: list[tuple[str, str, Callable[[], None]]],
    logo: Path | None,
) -> str:
    """Contenido completo de la barra lateral."""
    render_sidebar_logo(logo)
    active_module_key = render_sidebar_modules(module_definitions)
    render_sidebar_toolbar()
    render_theme_mode_control(st)
    return active_module_key
