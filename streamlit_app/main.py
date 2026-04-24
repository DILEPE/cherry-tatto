"""
Panel Streamlit para la API (Litestar): citas, contratos, plantillas y encuestas.

Ejecutar desde la raíz del repositorio (con el mismo Python/venv del proyecto):
  python -m streamlit run streamlit_app/main.py

Si `streamlit` no se reconoce como comando, usa siempre la forma `python -m streamlit`
(o instala dependencias: pip install -r requirements.txt dentro del venv activado).

Logo: coloca `branding.png` en `streamlit_app/assets/` o en `assets/` del proyecto.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Permite `from streamlit_app import ...` al ejecutar con Streamlit
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from app.domain.service_types import configured_service_types

from streamlit_app import api_client
from streamlit_app.validation import (
    validate_appointment,
    validate_contract,
    validate_report_dates,
    validate_survey,
    validate_template,
    validate_template_id,
)

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
        </style>
        """,
        unsafe_allow_html=True,
    )


def _logo_path() -> Path | None:
    for p in LOGO_CANDIDATES:
        if p.is_file():
            return p
    return None


def _show_validation_errors(errors) -> None:
    for e in errors:
        st.markdown(
            f'<div class="m-error"><strong>{e.field}</strong>: {e.message}</div>',
            unsafe_allow_html=True,
        )


def _api_error(payload) -> str:
    if isinstance(payload, dict):
        return str(payload.get("detail", payload))
    return str(payload)


def _sync_api_base_url() -> None:
    """Sincroniza la URL con el proceso; no reasigna la clave del text_input (Streamlit no lo permite)."""
    raw = st.session_state.get("api_base_url") or api_client.DEFAULT_BASE
    url = raw.strip().rstrip("/")
    os.environ["API_BASE_URL"] = url


def main() -> None:
    st.set_page_config(
        page_title="Cherry Ink · Rock City — Panel API",
        page_icon="🍒",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    if "api_base_url" not in st.session_state:
        st.session_state["api_base_url"] = os.getenv("API_BASE_URL", api_client.DEFAULT_BASE)

    _inject_material_neon_css()

    with st.sidebar:
        logo = _logo_path()
        if logo:
            st.image(str(logo), use_container_width=True)
        else:
            st.markdown('<p class="neon-title">CHERRY INK</p>', unsafe_allow_html=True)
            st.markdown('<p class="sub-lavender">Rock City Piercing</p>', unsafe_allow_html=True)
        st.markdown("---")
        st.caption("URL base de la API Litestar")
        st.text_input(
            "API_BASE_URL",
            key="api_base_url",
            label_visibility="collapsed",
            placeholder="http://127.0.0.1:5000",
        )
        _sync_api_base_url()

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

    st.markdown('<p class="neon-title">Panel de operaciones</p>', unsafe_allow_html=True)
    st.caption("Controles tipo Material · tema oscuro Cherry Ink / Rock City")

    tab_citas, tab_contratos, tab_plantillas, tab_encuestas, tab_reporte = st.tabs(
        [
            "Citas · Cherry Ink",
            "Contratos",
            "Plantillas",
            "Encuestas · Rock City",
            "Reporte (validación)",
        ]
    )

    with tab_citas:
        with st.expander("Nueva cita", expanded=True):
            c1, c2 = st.columns(2)
            with c1:
                name = st.text_input("Nombre cliente *", placeholder="Nombre y apellido")
                phone = st.text_input("Teléfono *", placeholder="+34 …")
                svc_options = list(configured_service_types())
                service = st.selectbox(
                    "Tipo de servicio (ENUM en MySQL) *",
                    options=svc_options,
                    index=0,
                    help="Debe coincidir con los valores del ENUM `service_type`. "
                    "Configura SERVICE_TYPE_ENUM_VALUES en .env si tu lista es distinta.",
                )
            with c2:
                date_str = st.text_input("Fecha cita *", placeholder="AAAA-MM-DD")
                detail = st.text_area(
                    "Detalle del trabajo",
                    placeholder="Ej. manga neotradicional, lóbulo, retoque…",
                    height=80,
                )
                deposit = st.number_input("Depósito (€)", min_value=0.0, value=0.0, step=10.0)

            if st.button("Crear cita", key="btn_appt_create"):
                valid, errs = validate_appointment(name, phone, service, date_str, detail, deposit)
                if not valid:
                    _show_validation_errors(errs)
                else:
                    payload = {
                        "name": name.strip(),
                        "phone": phone.strip(),
                        "service": service.strip(),
                        "date": date_str.strip(),
                        "detail": detail.strip() or None,
                        "deposit": float(deposit),
                    }
                    ok, code, data = api_client.post_appointment(payload)
                    if ok:
                        body = json.dumps(data, ensure_ascii=False) if isinstance(data, dict) else str(data)
                        st.markdown(f'<div class="m-success">Cita creada: {body}</div>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div class="m-error">Error HTTP {code}: {_api_error(data)}</div>', unsafe_allow_html=True)

        with st.expander("Listado de citas", expanded=False):
            if st.button("Refrescar listado", key="btn_appt_list"):
                ok, code, data = api_client.get_appointments()
                if ok and isinstance(data, list):
                    st.dataframe(data, use_container_width=True, hide_index=True)
                else:
                    st.markdown(f'<div class="m-error">HTTP {code}: {_api_error(data)}</div>', unsafe_allow_html=True)

    with tab_contratos:
        with st.expander("Firma de contrato", expanded=True):
            appt_id = st.number_input("ID cita *", min_value=0, value=0, step=1)
            is_minor = st.checkbox("Es menor de edad", value=False)
            template_id_con = st.number_input("ID plantilla (opcional, 0 = omitir)", min_value=0, value=0, step=1)
            signature = st.text_input("Firma cliente / referencia *", placeholder="Texto o hash de firma")
            tutor_signature = st.text_input("Firma tutor (si menor)", placeholder="Opcional")
            health_json = st.text_area(
                "Datos de salud (JSON objeto) *",
                height=160,
                placeholder='{"alergias":"ninguna","medicacion":"..."}',
            )
            if st.button("Enviar contrato", key="btn_contract"):
                tid = None if template_id_con == 0 else int(template_id_con)
                valid, errs, health = validate_contract(
                    int(appt_id), signature, health_json, tutor_signature, tid
                )
                if not valid or health is None:
                    _show_validation_errors(errs)
                else:
                    payload = {
                        "appointment_id": int(appt_id),
                        "is_minor": bool(is_minor),
                        "health_data": health,
                        "signature": signature.strip(),
                        "tutor_signature": tutor_signature.strip() or None,
                        "template_id": tid,
                    }
                    ok, code, data = api_client.post_contract(payload)
                    if ok:
                        body = json.dumps(data, ensure_ascii=False) if isinstance(data, dict) else str(data)
                        st.markdown(f'<div class="m-success">{body}</div>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div class="m-error">HTTP {code}: {_api_error(data)}</div>', unsafe_allow_html=True)

    with tab_plantillas:
        with st.expander("Listar plantillas", expanded=True):
            only_active = st.checkbox("Solo activas", value=False, key="tpl_only_active")
            if st.button("Cargar plantillas", key="btn_tpl_list"):
                ok, code, data = api_client.get_templates(only_active)
                if ok:
                    st.json(data if data is not None else [])
                else:
                    st.markdown(f'<div class="m-error">HTTP {code}: {_api_error(data)}</div>', unsafe_allow_html=True)

        with st.expander("Detalle por ID", expanded=False):
            tid_get = st.number_input("ID plantilla", min_value=1, value=1, step=1, key="tid_get")
            if st.button("Obtener plantilla", key="btn_tpl_get"):
                valid, errs = validate_template_id(int(tid_get))
                if not valid:
                    _show_validation_errors(errs)
                else:
                    ok, code, data = api_client.get_template(int(tid_get))
                    if ok:
                        st.json(data)
                    else:
                        st.markdown(f'<div class="m-error">HTTP {code}: {_api_error(data)}</div>', unsafe_allow_html=True)

        with st.expander("Crear plantilla", expanded=False):
            tname = st.text_input("Nombre *", key="tpl_name")
            tver = st.text_input("Versión * (ej. 1.0.0)", key="tpl_ver")
            tcontent = st.text_area("Contenido *", height=200, key="tpl_content")
            tactive = st.checkbox("Activa", value=True, key="tpl_active")
            if st.button("Crear", key="btn_tpl_create"):
                valid, errs = validate_template(tname, tver, tcontent, tactive)
                if not valid:
                    _show_validation_errors(errs)
                else:
                    payload = {
                        "id": None,
                        "name": tname.strip(),
                        "version": tver.strip(),
                        "content": tcontent.strip(),
                        "is_active": tactive,
                    }
                    ok, code, data = api_client.post_template(payload)
                    if ok:
                        body = json.dumps(data, ensure_ascii=False) if isinstance(data, dict) else str(data)
                        st.markdown(f'<div class="m-success">{body}</div>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div class="m-error">HTTP {code}: {_api_error(data)}</div>', unsafe_allow_html=True)

        with st.expander("Actualizar plantilla", expanded=False):
            tid_put = st.number_input("ID a actualizar", min_value=1, value=1, key="tid_put")
            tname_u = st.text_input("Nombre *", key="tpl_name_u")
            tver_u = st.text_input("Versión *", key="tpl_ver_u")
            tcontent_u = st.text_area("Contenido *", height=160, key="tpl_content_u")
            tactive_u = st.checkbox("Activa", value=True, key="tpl_active_u")
            if st.button("Actualizar", key="btn_tpl_put"):
                valid_id, errs_id = validate_template_id(int(tid_put))
                valid_f, errs_f = validate_template(tname_u, tver_u, tcontent_u, tactive_u)
                all_errs = errs_id + errs_f
                if all_errs:
                    _show_validation_errors(all_errs)
                else:
                    payload = {
                        "id": int(tid_put),
                        "name": tname_u.strip(),
                        "version": tver_u.strip(),
                        "content": tcontent_u.strip(),
                        "is_active": tactive_u,
                    }
                    ok, code, data = api_client.put_template(int(tid_put), payload)
                    if ok:
                        body = json.dumps(data, ensure_ascii=False) if isinstance(data, dict) else str(data)
                        st.markdown(f'<div class="m-success">{body}</div>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div class="m-error">HTTP {code}: {_api_error(data)}</div>', unsafe_allow_html=True)

        with st.expander("Eliminar plantilla", expanded=False):
            tid_del = st.number_input("ID a eliminar", min_value=1, value=1, key="tid_del")
            if st.button("Eliminar", key="btn_tpl_del", type="secondary"):
                valid, errs = validate_template_id(int(tid_del))
                if not valid:
                    _show_validation_errors(errs)
                else:
                    ok, code, data = api_client.delete_template(int(tid_del))
                    if ok:
                        body = json.dumps(data, ensure_ascii=False) if isinstance(data, dict) else str(data)
                        st.markdown(f'<div class="m-success">{body}</div>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div class="m-error">HTTP {code}: {_api_error(data)}</div>', unsafe_allow_html=True)

    with tab_encuestas:
        st.markdown('<p class="sub-lavender">Satisfacción y seguimiento — Rock City</p>', unsafe_allow_html=True)
        with st.expander("Nueva encuesta", expanded=True):
            s_appt = st.number_input("ID cita *", min_value=0, value=0, step=1, key="s_appt")
            s_rating = st.slider("Calificación (1–5)", 1, 5, 5)
            s_comments = st.text_area("Comentarios", max_chars=2000)
            s_rec = st.checkbox("Recomendaría el estudio", value=True)
            if st.button("Registrar encuesta", key="btn_survey"):
                valid, errs = validate_survey(int(s_appt), int(s_rating), s_comments)
                if not valid:
                    _show_validation_errors(errs)
                else:
                    payload = {
                        "appointment_id": int(s_appt),
                        "rating": int(s_rating),
                        "comments": s_comments.strip() or None,
                        "would_recommend": bool(s_rec),
                    }
                    ok, code, data = api_client.post_survey(payload)
                    if ok:
                        body = json.dumps(data, ensure_ascii=False) if isinstance(data, dict) else str(data)
                        st.markdown(f'<div class="m-success">{body}</div>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div class="m-error">HTTP {code}: {_api_error(data)}</div>', unsafe_allow_html=True)

        with st.expander("Listado encuestas", expanded=False):
            if st.button("Refrescar encuestas", key="btn_survey_list"):
                ok, code, data = api_client.get_surveys()
                if ok and isinstance(data, list):
                    st.dataframe(data, use_container_width=True, hide_index=True)
                else:
                    st.markdown(f'<div class="m-error">HTTP {code}: {_api_error(data)}</div>', unsafe_allow_html=True)

    with tab_reporte:
        with st.expander("Rango de fechas", expanded=True):
            st.caption("Validación en cliente; conecta aquí un endpoint de informes cuando exista en la API.")
            d1 = st.text_input("Inicio AAAA-MM-DD", key="r_start")
            d2 = st.text_input("Fin AAAA-MM-DD", key="r_end")
            if st.button("Validar rango", key="btn_report"):
                valid, errs = validate_report_dates(d1, d2)
                if not valid:
                    _show_validation_errors(errs)
                else:
                    st.success("Rango de fechas válido.")


if __name__ == "__main__":
    main()
