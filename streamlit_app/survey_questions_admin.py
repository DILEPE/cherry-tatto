"""Gestión de encuestas — vista simulador de encuesta."""
from __future__ import annotations

from typing import Any

import streamlit as st

from app.domain.survey_question_helpers import QUESTION_TYPES_NEEDING_OPTIONS
from streamlit_app import api_client
from streamlit_app.theme import get_panel_theme

_DLG_SURVEY_ROOT_HTML = '<div class="dlg-survey-root" data-survey-dlg="1" aria-hidden="true"></div>'

# ── Tipos ─────────────────────────────────────────────────────────────────

_CREATE_TYPES: list[tuple[str, str]] = [
    ("rating_1_5", "⭐ Estrellas 1–5"),
    ("yes_no",     "✅ Sí o No"),
    ("textarea",   "💬 Comentario"),
    ("text_short", "📝 Texto corto"),
    ("radio",      "📋 Una opción"),
    ("checkbox",   "☑ Varias opciones"),
    ("select",     "🔽 Lista"),
    ("number",     "🔢 Número"),
]
_ALL_TYPES: list[tuple[str, str]] = _CREATE_TYPES + [("text", "📄 Texto (histór.)")]
_TYPE_LABEL: dict[str, str] = dict(_ALL_TYPES)

_SCOPE_ICON:  dict[str, str] = {"tattoo": "🖊️", "piercing": "💉", "both": "🔵"}
_SCOPE_LABEL: dict[str, str] = {"tattoo": "Tatuaje", "piercing": "Piercing", "both": "Ambos"}
_SCOPE_KEYS:  tuple[str, ...] = ("tattoo", "piercing", "both")

# ── Helpers ───────────────────────────────────────────────────────────────

def _api_msg(payload: Any) -> str:
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


def _options_from_lines(blob: str) -> list[str]:
    return [ln.strip() for ln in blob.splitlines() if ln.strip()]


def _fetch_questions() -> list[dict[str, Any]]:
    ok, code, data = api_client.get_survey_questions(include_inactive=True)
    if not ok or not isinstance(data, list):
        st.error(f"No se pudieron cargar las preguntas (HTTP {code}): {_api_msg(data)}")
        return []
    return data


def _preview_text(q: dict[str, Any]) -> str:
    qtype = str(q.get("question_type") or "text_short")
    opts: list[str] = [str(o) for o in (q.get("options") or [])]
    if qtype == "rating_1_5":
        return "☆  ☆  ☆  ☆  ☆  ← el cliente elige del 1 al 5"
    if qtype == "yes_no":
        return "○  Sí      ○  No"
    if qtype in ("text", "textarea"):
        return "_El cliente escribe un comentario…_"
    if qtype == "text_short":
        return "_El cliente escribe una respuesta corta…_"
    if qtype == "number":
        return "_El cliente escribe un número_"
    if qtype == "radio":
        return ("  ·  ".join(f"○ {o}" for o in opts[:5]) + ("…" if len(opts) > 5 else "")) if opts else "_⚠ Sin opciones — edita la pregunta para añadir_"
    if qtype == "checkbox":
        return ("  ·  ".join(f"□ {o}" for o in opts[:5]) + ("…" if len(opts) > 5 else "")) if opts else "_⚠ Sin opciones — edita la pregunta para añadir_"
    if qtype == "select":
        return f"▼  {opts[0]}  (lista desplegable)" if opts else "▼  (lista desplegable)"
    return ""


def _swap_order(a: dict[str, Any], b: dict[str, Any]) -> None:
    sa, sb = int(a.get("sort_order") or 0), int(b.get("sort_order") or 0)
    new_sa, new_sb = (sb, sa) if sa != sb else (min(sa, sb), max(sa, sb) + 1)
    ok1, _, _ = api_client.put_survey_question(int(a["id"]), {"sort_order": new_sa})
    ok2, _, _ = api_client.put_survey_question(int(b["id"]), {"sort_order": new_sb})
    if ok1 and ok2:
        st.rerun()
    else:
        st.error("No se pudo reordenar.")

# ── Diálogos ──────────────────────────────────────────────────────────────

def _mark_survey_dialog_scope() -> None:
    """Marcador para CSS de diálogo en modo claro (styles/_theme_survey_questions.css)."""
    st.markdown(_DLG_SURVEY_ROOT_HTML, unsafe_allow_html=True)
    if get_panel_theme() == "light":
        st.markdown(
            """
            <style>
            div[data-testid="stDialog"]:has(.dlg-survey-root) [role="dialog"],
            div[data-testid="stDialog"]:has([data-survey-dlg]) [role="dialog"] {
              background: #ffffff !important;
              background-color: #ffffff !important;
              color: #1e293b !important;
            }
            div[data-testid="stDialog"]:has(.dlg-survey-root) [data-testid="stVerticalBlock"],
            div[data-testid="stDialog"]:has(.dlg-survey-root) [data-testid="stHorizontalBlock"] {
              background: #ffffff !important;
              background-color: #ffffff !important;
            }
            div[data-testid="stDialog"]:has(.dlg-survey-root) [data-testid="stMarkdownContainer"] p,
            div[data-testid="stDialog"]:has(.dlg-survey-root) [data-testid="stMarkdownContainer"] strong,
            div[data-testid="stDialog"]:has(.dlg-survey-root) [data-testid="stRadio"] label,
            div[data-testid="stDialog"]:has(.dlg-survey-root) [data-testid="stRadio"] label p {
              color: #334155 !important;
            }
            div[data-testid="stDialog"]:has(.dlg-survey-root) [data-testid="stTextInput"] input,
            div[data-testid="stDialog"]:has(.dlg-survey-root) textarea {
              background: #ffffff !important;
              color: #1e293b !important;
              border-color: rgba(15, 23, 42, 0.18) !important;
            }
            div[data-testid="stDialog"]:has(.dlg-survey-root) [data-testid="stButton"] button[data-testid="baseButton-primary"],
            div[data-testid="stDialog"]:has(.dlg-survey-root) [data-testid="stButton"] button[kind="primary"] {
              background-image: linear-gradient(180deg, #ff5fb8 0%, #ff007f 52%, #d90064 100%) !important;
              background-color: #ff007f !important;
              color: #ffffff !important;
            }
            div[data-testid="stDialog"]:has(.dlg-survey-root) [data-testid="stButton"] button[data-testid="baseButton-primary"] *,
            div[data-testid="stDialog"]:has(.dlg-survey-root) [data-testid="stButton"] button[kind="primary"] * {
              color: #ffffff !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )


def _type_picker(key: str, default_type: str, *, all_types: bool = False) -> str:
    """Radio horizontal con tipos amigables. Devuelve el código de tipo seleccionado."""
    types = _ALL_TYPES if all_types else _CREATE_TYPES
    labels = [lbl for _, lbl in types]
    keys   = [k   for k,  _ in types]
    default_lbl = _TYPE_LABEL.get(default_type, labels[0])
    if default_lbl not in labels:
        default_lbl = labels[0]
    picked = st.radio(
        "Tipo",
        options=labels,
        index=labels.index(default_lbl),
        horizontal=True,
        label_visibility="collapsed",
        key=key,
    )
    return keys[labels.index(picked)] if picked in labels else default_type


def _scope_picker(key: str, default_scope: str) -> str:
    safe = default_scope if default_scope in _SCOPE_KEYS else "both"
    picked = st.radio(
        "Servicio",
        options=list(_SCOPE_KEYS),
        format_func=lambda k: f"{_SCOPE_ICON[k]}  {_SCOPE_LABEL[k]}",
        horizontal=True,
        index=list(_SCOPE_KEYS).index(safe),
        label_visibility="collapsed",
        key=key,
    )
    return str(picked) if picked in _SCOPE_KEYS else safe


@st.dialog("Agregar pregunta", width="large", dismissible=False)
def _dlg_new() -> None:
    _mark_survey_dialog_scope()
    st.markdown("**1. ¿Qué tipo de respuesta quieres recoger?**")
    chosen_type = _type_picker("sq_dlg_new_type", "rating_1_5")

    st.markdown("**2. Escribe la pregunta que verá el cliente:**")
    st.text_input(
        "Texto",
        placeholder="Ej: ¿Cómo calificarías tu experiencia con nosotros?",
        max_chars=500,
        label_visibility="collapsed",
        key="sq_dlg_new_lbl",
    )

    if chosen_type in QUESTION_TYPES_NEEDING_OPTIONS:
        st.markdown("**3. Opciones de respuesta** _(una por línea, mínimo 2)_")
        st.text_area(
            "Opciones",
            placeholder="Muy buena\nBuena\nRegular\nMala",
            height=110,
            label_visibility="collapsed",
            key="sq_dlg_new_opts",
        )

    st.markdown("**¿Para qué servicio aplica?**")
    scope = _scope_picker("sq_dlg_new_scope", "both")

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Cancelar", use_container_width=True, key="sq_dlg_new_cancel"):
            st.rerun()
    with c2:
        if st.button("💾 Guardar", type="primary", use_container_width=True, key="sq_dlg_new_save"):
            lbl = str(st.session_state.get("sq_dlg_new_lbl") or "").strip()
            if not lbl:
                st.warning("Escribe el texto de la pregunta.")
                return
            payload: dict[str, Any] = {
                "label": lbl,
                "question_type": chosen_type,
                "sort_order": 9999,
                "contract_kind": scope,
                "is_active": True,
            }
            if chosen_type in QUESTION_TYPES_NEEDING_OPTIONS:
                opts = _options_from_lines(str(st.session_state.get("sq_dlg_new_opts") or ""))
                if len(opts) < 2:
                    st.warning("Añade al menos dos opciones.")
                    return
                payload["options"] = opts
            ok, code, data = api_client.post_survey_question(payload)
            if ok:
                st.rerun()
            else:
                st.error(f"No se pudo crear (HTTP {code}): {_api_msg(data)}")


@st.dialog("Editar pregunta", width="large", dismissible=False)
def _dlg_edit(q: dict[str, Any]) -> None:
    _mark_survey_dialog_scope()
    qid = int(q["id"])
    cur_type  = str(q.get("question_type") or "text_short")
    cur_opts  = [str(o) for o in (q.get("options") or [])]
    cur_scope = str(q.get("contract_kind") or "both")

    st.markdown("**1. Tipo de respuesta:**")
    chosen_type = _type_picker(f"sq_dlg_edit_type_{qid}", cur_type, all_types=True)

    st.markdown("**2. Texto de la pregunta:**")
    st.text_input(
        "Texto",
        value=str(q.get("label") or ""),
        max_chars=500,
        label_visibility="collapsed",
        key=f"sq_dlg_edit_lbl_{qid}",
    )

    if chosen_type in QUESTION_TYPES_NEEDING_OPTIONS:
        st.markdown("**3. Opciones** _(una por línea)_")
        st.text_area(
            "Opciones",
            value="\n".join(cur_opts),
            height=110,
            label_visibility="collapsed",
            key=f"sq_dlg_edit_opts_{qid}",
        )

    st.markdown("**¿Para qué servicio aplica?**")
    scope = _scope_picker(f"sq_dlg_edit_scope_{qid}", cur_scope)

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Cancelar", use_container_width=True, key=f"sq_dlg_edit_cancel_{qid}"):
            st.rerun()
    with c2:
        if st.button("💾 Guardar cambios", type="primary", use_container_width=True, key=f"sq_dlg_edit_save_{qid}"):
            lbl = str(st.session_state.get(f"sq_dlg_edit_lbl_{qid}") or "").strip()
            if not lbl:
                st.warning("El texto no puede estar vacío.")
                return
            body: dict[str, Any] = {
                "label": lbl,
                "question_type": chosen_type,
                "sort_order": int(q.get("sort_order") or 0),
                "contract_kind": scope,
                "is_active": bool(q.get("is_active", True)),
            }
            if chosen_type in QUESTION_TYPES_NEEDING_OPTIONS:
                opts = _options_from_lines(str(st.session_state.get(f"sq_dlg_edit_opts_{qid}") or ""))
                if len(opts) < 2:
                    st.warning("Define al menos dos opciones.")
                    return
                body["options"] = opts
            ok, code, data = api_client.put_survey_question(qid, body)
            if ok:
                st.rerun()
            else:
                st.error(f"No se pudo guardar (HTTP {code}): {_api_msg(data)}")


@st.dialog("Eliminar pregunta", width="small", dismissible=False)
def _dlg_delete(q: dict[str, Any]) -> None:
    _mark_survey_dialog_scope()
    qid = int(q["id"])
    st.markdown(f"¿Eliminar esta pregunta?")
    st.info(f"**«{q.get('label', '')}»**")

    ok_i, _, raw_i = api_client.get_survey_question_deletion_impact(qid)
    if ok_i and isinstance(raw_i, dict):
        n = int(raw_i.get("registered_answers") or 0)
        if n > 0:
            st.warning(
                f"Esta pregunta tiene **{n}** respuesta(s) de clientes guardadas. "
                "Al eliminarla esas estadísticas se perderán del reporte."
            )
        else:
            st.caption("Esta pregunta no tiene respuestas guardadas.")

    confirm = st.checkbox("Sí, quiero eliminarla definitivamente", key=f"sq_dlg_del_confirm_{qid}")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Cancelar", use_container_width=True, key=f"sq_dlg_del_cancel_{qid}"):
            st.rerun()
    with c2:
        if st.button(
            "🗑 Eliminar",
            type="primary",
            disabled=not confirm,
            use_container_width=True,
            key=f"sq_dlg_del_go_{qid}",
        ):
            ok_d, code_d, raw_d = api_client.delete_survey_question(qid)
            if ok_d:
                st.rerun()
            else:
                st.error(f"Error (HTTP {code_d}): {_api_msg(raw_d)}")

# ── Tarjeta de pregunta ───────────────────────────────────────────────────

def _render_card(
    q: dict[str, Any],
    prev_q: dict[str, Any] | None,
    next_q: dict[str, Any] | None,
    *,
    is_active: bool,
) -> None:
    qid   = int(q["id"])
    scope = str(q.get("contract_kind") or "both")
    if scope not in _SCOPE_LABEL:
        scope = "both"
    qtype = str(q.get("question_type") or "text_short")

    with st.container(border=True):
        col_text, col_btns = st.columns([6, 2])

        with col_text:
            st.markdown(f"**{q.get('label', '')}**")
            prev = _preview_text(q)
            if prev:
                st.caption(prev)
            type_lbl  = _TYPE_LABEL.get(qtype, qtype)
            scope_str = f"{_SCOPE_ICON.get(scope, '')} {_SCOPE_LABEL.get(scope, scope)}"
            st.caption(f"{scope_str}  ·  {type_lbl}")

        with col_btns:
            if is_active:
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    if st.button("↑", key=f"sq_up_{qid}", disabled=prev_q is None,
                                 help="Subir", use_container_width=True):
                        if prev_q:
                            _swap_order(q, prev_q)
                with c2:
                    if st.button("↓", key=f"sq_dn_{qid}", disabled=next_q is None,
                                 help="Bajar", use_container_width=True):
                        if next_q:
                            _swap_order(q, next_q)
                with c3:
                    if st.button("✏️", key=f"sq_edit_{qid}", help="Editar",
                                 use_container_width=True):
                        _dlg_edit(q)
                with c4:
                    if st.button("🗑️", key=f"sq_del_{qid}", help="Eliminar",
                                 use_container_width=True):
                        _dlg_delete(q)
            else:
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("✅ Activar", key=f"sq_act_{qid}", use_container_width=True):
                        ok_a, _, err_a = api_client.put_survey_question(qid, {"is_active": True})
                        if ok_a:
                            st.rerun()
                        else:
                            st.error(_api_msg(err_a))
                with c2:
                    if st.button("🗑 Borrar", key=f"sq_del_i_{qid}", use_container_width=True):
                        _dlg_delete(q)

# ── Vista principal ───────────────────────────────────────────────────────

def render_survey_questions_tab() -> None:
    questions = _fetch_questions()

    active = sorted(
        [q for q in questions if q.get("is_active")],
        key=lambda x: (int(x.get("sort_order") or 0), int(x.get("id") or 0)),
    )
    inactive = sorted(
        [q for q in questions if not q.get("is_active")],
        key=lambda x: (int(x.get("sort_order") or 0), int(x.get("id") or 0)),
    )

    # Encabezado
    h1, h2 = st.columns([5, 2])
    with h1:
        st.markdown(
            '<p class="neon-title" style="font-size:1.1rem;">Encuesta de satisfacción</p>',
            unsafe_allow_html=True,
        )
        if active:
            st.caption(
                f"{len(active)} pregunta(s) activa(s)  ·  "
                "usa ↑ ↓ para cambiar el orden en que las verá el cliente"
            )
        else:
            st.caption("Crea la primera pregunta con el botón de la derecha.")
    with h2:
        if st.button("＋ Agregar pregunta", type="primary",
                     use_container_width=True, key="sq_btn_add"):
            _dlg_new()

    st.markdown("---")

    # Preguntas activas
    if not active:
        st.info(
            "La encuesta está vacía. Cuando añadas preguntas activas, "
            "aquí verás una vista previa de cómo las verá el cliente al firmar."
        )
    else:
        for i, q in enumerate(active):
            _render_card(
                q,
                prev_q=active[i - 1] if i > 0 else None,
                next_q=active[i + 1] if i < len(active) - 1 else None,
                is_active=True,
            )

    # Preguntas inactivas (plegadas)
    if inactive:
        st.markdown("---")
        with st.expander(
            f"Preguntas inactivas ({len(inactive)}) — no aparecen en la encuesta"
        ):
            st.caption("Actívalas para incluirlas en la encuesta al firmar contrato.")
            for q in inactive:
                _render_card(q, prev_q=None, next_q=None, is_active=False)
