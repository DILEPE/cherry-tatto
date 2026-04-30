"""
Panel Streamlit para la API (Litestar): citas, contratos, plantillas y encuestas.

Ejecutar desde la raíz del repositorio (con el mismo Python/venv del proyecto):
  python -m streamlit run streamlit_app/main.py

Si `streamlit` no se reconoce como comando, usa siempre la forma `python -m streamlit`
(o instala dependencias: pip install -r requirements.txt dentro del venv activado).

Logo: coloca `branding.png` en `streamlit_app/assets/` o en `assets/` del proyecto.
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

import streamlit as st

from streamlit_app import api_client
from streamlit_app.citas_tab import render_citas_tab
from streamlit_app.contract_read_view import render_contract_read_view
from streamlit_app.contract_signing import render_contract_signing_view
from streamlit_app.contracts_admin import render_contract_admin_tab
from streamlit_app.customers_management import render_customers_management_tab

LOGO_CANDIDATES = [
    Path(__file__).resolve().parent / "assets" / "branding.png",
    Path(__file__).resolve().parent.parent / "assets" / "branding.png",
]


def _inject_material_neon_css() -> None:
    st.markdown(
        """
        <style>
          @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
          html, body, [class*="css"]  { font-family: 'Inter', 'Segoe UI', sans-serif !important; }
          [data-testid="stAppViewContainer"] {
            background: radial-gradient(ellipse 120% 80% at 50% -20%, rgba(255,0,127,0.12), transparent 55%),
                        radial-gradient(ellipse 80% 50% at 100% 50%, rgba(167,154,255,0.08), transparent 45%),
                        #000000;
          }
          [data-testid="stHeader"] { background: rgba(0,0,0,0.85) !important; }
          [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #121212 0%, #0d0d0d 100%) !important;
            border-right: 1px solid rgba(255,255,255,0.08);
          }
          div[data-baseweb="tab-highlight"] { background-color: #FF007F !important; box-shadow: 0 0 12px rgba(255,0,127,0.45); }
          [data-baseweb="tab"] { color: #e0e0e0 !important; font-weight: 600; }
          [data-baseweb="tab"]:hover { color: #FF007F !important; }
          [data-testid="stExpander"] {
            background: #1E1E1E !important;
            border: 1px solid rgba(255,255,255,0.12) !important;
            border-radius: 12px !important;
            box-shadow: 0 2px 8px rgba(0,0,0,0.45);
          }
          .neon-title {
            color: #fff;
            font-weight: 700;
            font-size: 1.35rem;
            letter-spacing: 0.02em;
            text-shadow: 0 0 18px rgba(255,0,127,0.35);
          }
          .sub-lavender { color: #A79AFF; font-weight: 600; font-size: 0.95rem; }
          .m-error {
            background: rgba(207,102,121,0.15);
            border: 1px solid #CF6679;
            color: #FFB4A9;
            border-radius: 8px;
            padding: 0.75rem 1rem;
            margin: 0.5rem 0 1rem 0;
            font-size: 0.9rem;
          }
          .m-success {
            background: rgba(105,240,174,0.12);
            border: 1px solid #69F0AE;
            color: #B9F6CA;
            border-radius: 8px;
            padding: 0.75rem 1rem;
            margin: 0.5rem 0 1rem 0;
          }
          div.stButton > button:first-child {
            border-radius: 999px !important;
            font-weight: 600 !important;
            border: 1px solid rgba(255,0,127,0.55) !important;
            box-shadow: 0 0 16px rgba(255,0,127,0.25) !important;
          }
          div.stButton > button[kind="secondary"] {
            border-color: rgba(167,154,255,0.5) !important;
            box-shadow: 0 0 12px rgba(167,154,255,0.2) !important;
          }
          hr { border-color: rgba(255,255,255,0.1) !important; }
          [data-testid="stTextInput"] input,
          [data-testid="stNumberInput"] input,
          [data-testid="stTextArea"] textarea,
          [data-testid="stSelectbox"] div[data-baseweb="select"] > div {
            background-color: #2e2e2e !important;
            color: #f2f2f2 !important;
            border-color: rgba(255,255,255,0.22) !important;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _logo_path() -> Path | None:
    for p in LOGO_CANDIDATES:
        if p.is_file():
            return p
    return None


def _api_error(payload) -> str:
    if isinstance(payload, dict):
        return str(payload.get("detail", payload))
    return str(payload)


def main() -> None:
    st.set_page_config(
        page_title="Cherry Ink · Rock City — Panel API",
        page_icon="🍒",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _inject_material_neon_css()

    # URL dedicada para firma de contratos:
    # ?view=contract_sign&appointment_id=<id>
    view = st.query_params.get("view")
    if view == "contract_sign":
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

    with st.sidebar:
        logo = _logo_path()
        if logo:
            st.image(str(logo), use_container_width=True)
        else:
            st.markdown('<p class="neon-title">CHERRY INK</p>', unsafe_allow_html=True)
            st.markdown('<p class="sub-lavender">Rock City Piercing</p>', unsafe_allow_html=True)
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

    st.markdown('<p class="neon-title">Panel de operaciones</p>', unsafe_allow_html=True)

    tab_citas, tab_customers, tab_admin_contratos, tab_encuestas, tab_reporte = st.tabs(
        [
            "Gestión citas",
            "Gestión de clientes",
            "Gestión contratos",
            "Gestión encuesta",
            "Gestión reporte",
        ]
    )

    with tab_citas:
        render_citas_tab()

    with tab_customers:
        render_customers_management_tab()

    with tab_admin_contratos:
        render_contract_admin_tab()

    with tab_encuestas:
        st.info("Gestión encuesta — en construcción.")

    with tab_reporte:
        st.info("Gestión reporte — en construcción.")


if __name__ == "__main__":
    main()
