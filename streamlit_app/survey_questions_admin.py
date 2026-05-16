"""Streamlit: administración de preguntas dinámicas para encuestas de satisfacción."""
from __future__ import annotations

from typing import Any, Dict, List

import streamlit as st

from app.domain.contract_kinds import SCOPE_LABEL_ES
from app.domain.survey_question_helpers import (
    QUESTION_TYPES_NEEDING_OPTIONS,
    question_type_label_es,
)
from streamlit_app import api_client


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


_TYPE_OPTIONS: tuple[str, ...] = (
    "rating_1_5",
    "yes_no",
    "text",
    "textarea",
    "text_short",
    "number",
    "radio",
    "checkbox",
    "select",
)

_CONTRACT_KIND_OPTIONS: tuple[str, ...] = ("tattoo", "piercing", "both")


def _options_from_lines(blob: str) -> List[str]:
    return [ln.strip() for ln in blob.splitlines() if ln.strip()]


def _fetch_questions(include_inactive: bool = True) -> List[Dict[str, Any]]:
    ok, code, data = api_client.get_survey_questions(include_inactive=include_inactive)
    if not ok or not isinstance(data, list):
        st.error(f"No se pudieron cargar las preguntas (HTTP {code}): {_api_msg(data)}")
        return []
    return data


def render_survey_questions_tab() -> None:
    st.markdown('<p class="neon-title" style="font-size:1.1rem;">Gestión de preguntas — encuesta</p>', unsafe_allow_html=True)
    with st.expander("Tipos soportados (misma API que el backend)", expanded=False):
        st.markdown(
            "| Tipo en panel | Uso |\n"
            "|---|---|\n"
            "| Escala 1–5 | Calificación numérica fija 1–5 |\n"
            "| Sí / No | Booleano |\n"
            "| Texto libre (histórico) | Texto largo (compatibilidad) |\n"
            "| Área de texto | Varias líneas |\n"
            "| Texto en una línea | Campo corto |\n"
            "| Numérico | Número decimal (respuesta en `answer_number`) |\n"
            "| Radio | Una opción; rellena **opciones** (≥2 líneas) |\n"
            "| Casillas | Varias opciones; mismo campo de opciones |\n"
            "| Lista desplegable | Una opción; mismo campo de opciones |\n"
        )

    questions = _fetch_questions(include_inactive=True)

    st.markdown("##### Crear pregunta")
    c_type, c_kind, c_hint = st.columns([1, 1, 1])
    with c_type:
        create_qtype = st.selectbox(
            "Tipo de respuesta",
            options=list(_TYPE_OPTIONS),
            format_func=question_type_label_es,
            index=0,
            key="sq_create_qtype",
            help="Radio, casillas y lista desplegable requieren al menos 2 opciones en el cuadro de abajo.",
        )
    with c_kind:
        st.selectbox(
            "Ámbito",
            options=list(_CONTRACT_KIND_OPTIONS),
            format_func=lambda k: SCOPE_LABEL_ES[str(k)],
            index=0,
            key="sq_create_contract_kind",
            help="**Tatuaje**, **piercing** o **ambas**: en la firma se muestran las de su tipo más las marcadas para ambos servicios.",
        )
    with c_hint:
        if create_qtype in QUESTION_TYPES_NEEDING_OPTIONS:
            st.info("Rellena **Opciones** (una por línea) y luego el texto de la pregunta en el formulario.")

    if create_qtype in QUESTION_TYPES_NEEDING_OPTIONS:
        st.text_area(
            "Opciones (una por línea)",
            placeholder="Opción A\nOpción B\nOpción C",
            height=160,
            key="sq_create_opts",
            help="Mínimo 2 líneas no vacías. Aparece en cuanto eliges lista desplegable, radio o casillas.",
        )

    with st.form("sq_create_form", clear_on_submit=True):
        label = st.text_input(
            "Texto de la pregunta",
            placeholder="¿Cómo calificaría la limpieza del local?",
            max_chars=500,
            key="sq_create_label",
        )
        r1, r2 = st.columns(2)
        with r1:
            sort_order = st.number_input("Orden (menor = primero)", min_value=0, max_value=9999, value=0, step=1)
        with r2:
            is_active = st.checkbox("Pregunta activa", value=True)
        submitted = st.form_submit_button("Crear pregunta", use_container_width=True)
        if submitted:
            qt = str(st.session_state.get("sq_create_qtype", create_qtype))
            opts_raw = str(st.session_state.get("sq_create_opts", "")) if qt in QUESTION_TYPES_NEEDING_OPTIONS else ""
            if not (label or "").strip():
                st.warning("Escribe el texto de la pregunta.")
            else:
                opt_list: List[str] | None = None
                if qt in QUESTION_TYPES_NEEDING_OPTIONS:
                    opt_list = _options_from_lines(opts_raw)
                    if len(opt_list) < 2:
                        st.warning("Define al menos dos opciones (una por línea) en el cuadro de opciones.")
                        opt_list = None
                if opt_list is not None or qt not in QUESTION_TYPES_NEEDING_OPTIONS:
                    payload: Dict[str, Any] = {
                        "label": label.strip(),
                        "question_type": qt,
                        "sort_order": int(sort_order),
                        "contract_kind": str(st.session_state.get("sq_create_contract_kind", "tattoo")),
                        "is_active": bool(is_active),
                    }
                    if qt in QUESTION_TYPES_NEEDING_OPTIONS:
                        payload["options"] = opt_list
                    ok, code, data = api_client.post_survey_question(payload)
                    if ok:
                        st.success("Pregunta creada.")
                        st.session_state["sq_create_qtype"] = _TYPE_OPTIONS[0]
                        st.session_state["sq_create_contract_kind"] = "tattoo"
                        st.session_state.pop("sq_create_opts", None)
                        st.rerun()
                    else:
                        st.error(f"No se pudo crear (HTTP {code}): {_api_msg(data)}")

    st.markdown("##### Editar pregunta")
    if not questions:
        st.info("Aún no hay preguntas. Crea la primera arriba.")
        options: list[int] = []
        labels_map: Dict[int, str] = {}
    else:
        by_id = {int(q["id"]): q for q in questions}
        options = sorted(by_id.keys())
        labels_map: Dict[int, str] = {}
        for i in options:
            q = by_id[i]
            ck_lbl = SCOPE_LABEL_ES.get(str(q.get("contract_kind") or "tattoo"), "?")
            labels_map[i] = f"{i} — [{ck_lbl}] {(q.get('label') or '')[:52]}"
        edit_pick = st.selectbox(
            "Seleccionar pregunta",
            options=options,
            format_func=lambda i: labels_map[i],
            key="sq_edit_pick",
        )
        qcur = by_id[edit_pick]
        cur_type = str(qcur.get("question_type") or "text_short")
        if cur_type not in _TYPE_OPTIONS:
            cur_type = "text_short"
        cur_opts = qcur.get("options")
        if not isinstance(cur_opts, list):
            cur_opts = []
        opts_default = "\n".join(str(x) for x in cur_opts)

        prev_id = st.session_state.get("sq_edit_prev_id")
        if prev_id != edit_pick:
            if prev_id is not None:
                st.session_state.pop(f"sq_edit_et_{prev_id}", None)
                st.session_state.pop(f"sq_edit_eo_{prev_id}", None)
                st.session_state.pop(f"sq_edit_lab_{prev_id}", None)
                st.session_state.pop(f"sq_edit_ck_{prev_id}", None)
            st.session_state["sq_edit_prev_id"] = edit_pick

        if not bool(qcur.get("is_active")):
            st.warning(
                "Esta pregunta está **inactiva**: no aparece en el cuestionario de firma de contrato. "
                "Actívala para ver y editar tipo, opciones, texto y orden."
            )
            if st.button("Activar pregunta", key=f"sq_edit_activate_{edit_pick}"):
                ok_a, code_a, data_a = api_client.put_survey_question(edit_pick, {"is_active": True})
                if ok_a:
                    st.success("Pregunta activada.")
                    st.rerun()
                else:
                    st.error(f"No se pudo activar (HTTP {code_a}): {_api_msg(data_a)}")
        else:
            show_editor = st.checkbox(
                "Editar contenido (tipo, opciones, ámbito, texto y orden)",
                value=True,
                key=f"sq_edit_show_{edit_pick}",
                help="Desmarcar oculta el formulario si solo quieres revisar qué pregunta está seleccionada.",
            )
            if not show_editor:
                st.caption("Marca **Editar contenido** para mostrar el cuerpo del formulario.")
            else:
                k_et = f"sq_edit_et_{edit_pick}"
                k_eo = f"sq_edit_eo_{edit_pick}"
                k_lab = f"sq_edit_lab_{edit_pick}"
                k_ck = f"sq_edit_ck_{edit_pick}"
                _cur_ck = str(qcur.get("contract_kind") or "tattoo").strip().lower()
                if _cur_ck not in ("tattoo", "piercing", "both"):
                    _cur_ck = "tattoo"
                if k_et not in st.session_state:
                    st.session_state[k_et] = cur_type
                if k_eo not in st.session_state:
                    st.session_state[k_eo] = opts_default
                if k_lab not in st.session_state:
                    st.session_state[k_lab] = str(qcur.get("label") or "")
                if k_ck not in st.session_state:
                    st.session_state[k_ck] = _cur_ck

                st.caption(
                    "Cambia el **tipo**, las **opciones** y el **ámbito** aquí; el texto y el orden van con **Guardar**."
                )
                ec1, ec2 = st.columns([1, 1])
                with ec1:
                    st.selectbox(
                        "Tipo (edición)",
                        options=list(_TYPE_OPTIONS),
                        format_func=question_type_label_es,
                        key=k_et,
                    )
                with ec2:
                    et_now = str(st.session_state.get(k_et, cur_type))
                    if et_now in QUESTION_TYPES_NEEDING_OPTIONS:
                        st.info("Edita las opciones en el recuadro de abajo.")

                if et_now in QUESTION_TYPES_NEEDING_OPTIONS:
                    st.text_area(
                        "Opciones (una por línea)",
                        height=160,
                        key=k_eo,
                        help="Mínimo 2 opciones para radio, casillas o lista desplegable.",
                    )

                st.selectbox(
                    "Ámbito (tatuaje / piercing / ambas)",
                    options=list(_CONTRACT_KIND_OPTIONS),
                    format_func=lambda k: SCOPE_LABEL_ES[str(k)],
                    key=k_ck,
                    help="Fuera del formulario para que el cambio se registre al primer clic al guardar.",
                )

                with st.form(f"sq_edit_form_{edit_pick}"):
                    st.text_input("Texto de la pregunta", max_chars=500, key=k_lab)
                    eo1, eo2 = st.columns(2)
                    with eo1:
                        esort = st.number_input(
                            "Orden",
                            min_value=0,
                            max_value=9999,
                            value=int(qcur.get("sort_order") or 0),
                            step=1,
                        )
                    with eo2:
                        eactive = st.checkbox("Activa", value=bool(qcur.get("is_active", True)))
                    if st.form_submit_button("Guardar cambios", use_container_width=True):
                        et = str(st.session_state.get(k_et, cur_type))
                        el = str(st.session_state.get(k_lab, ""))
                        ekind = str(st.session_state.get(k_ck, _cur_ck))
                        if ekind not in ("tattoo", "piercing", "both"):
                            ekind = _cur_ck
                        if not el.strip():
                            st.warning("El texto de la pregunta no puede estar vacío.")
                        elif et in QUESTION_TYPES_NEEDING_OPTIONS:
                            ol = _options_from_lines(str(st.session_state.get(k_eo, "")))
                            if len(ol) < 2:
                                st.warning("Define al menos dos opciones (una por línea).")
                            else:
                                body: Dict[str, Any] = {
                                    "label": el.strip(),
                                    "question_type": et,
                                    "sort_order": int(esort),
                                    "contract_kind": ekind,
                                    "is_active": bool(eactive),
                                    "options": ol,
                                }
                                ok, code, data = api_client.put_survey_question(edit_pick, body)
                                if ok:
                                    st.success("Cambios guardados.")
                                    st.session_state.pop(k_et, None)
                                    st.session_state.pop(k_eo, None)
                                    st.session_state.pop(k_lab, None)
                                    st.session_state.pop(k_ck, None)
                                    st.rerun()
                                else:
                                    st.error(f"Error (HTTP {code}): {_api_msg(data)}")
                        else:
                            body = {
                                "label": el.strip(),
                                "question_type": et,
                                "sort_order": int(esort),
                                "contract_kind": ekind,
                                "is_active": bool(eactive),
                            }
                            ok, code, data = api_client.put_survey_question(edit_pick, body)
                            if ok:
                                st.success("Cambios guardados.")
                                st.session_state.pop(k_et, None)
                                st.session_state.pop(k_eo, None)
                                st.session_state.pop(k_lab, None)
                                st.session_state.pop(k_ck, None)
                                st.rerun()
                            else:
                                st.error(f"Error (HTTP {code}): {_api_msg(data)}")

    st.markdown("##### Eliminar pregunta")
    st.caption(
        "Al eliminar se borran también todas las respuestas históricas vinculadas a esa pregunta "
        "(no se pueden recuperar para el reporte)."
    )
    if questions:
        del_pick = st.selectbox(
            "Pregunta a eliminar",
            options=options,
            format_func=lambda i: labels_map[i],
            key="sq_del_pick",
        )
        if st.button("Revisar impacto antes de eliminar", key="sq_del_preview"):
            st.session_state["_sq_del_impact_id"] = del_pick
        impact_id: int | None = st.session_state.get("_sq_del_impact_id")
        if impact_id == del_pick:
            ok_i, code_i, raw_i = api_client.get_survey_question_deletion_impact(del_pick)
            if ok_i and isinstance(raw_i, dict):
                n = int(raw_i.get("registered_answers") or 0)
                lbl = str(raw_i.get("label") or "")
                st.warning(
                    f"**«{lbl}»** tiene **{n}** respuesta(s) guardada(s) en encuestas. "
                    "Si confirmas la eliminación, **esas mediciones desaparecerán** del reporte y de la base de datos."
                )
                confirm = st.checkbox(
                    "Entiendo que se borrarán las estadísticas y respuestas de esta pregunta.",
                    key="sq_del_confirm",
                )
                if st.button("Eliminar definitivamente", type="primary", disabled=not confirm, key="sq_del_go"):
                    ok_d, code_d, raw_d = api_client.delete_survey_question(del_pick)
                    if ok_d:
                        st.session_state.pop("_sq_del_impact_id", None)
                        st.success("Pregunta eliminada.")
                        st.rerun()
                    else:
                        st.error(f"Error (HTTP {code_d}): {_api_msg(raw_d)}")
            else:
                st.error(f"No se pudo consultar el impacto (HTTP {code_i}): {_api_msg(raw_i)}")

    st.markdown("##### Vista previa del orden")
    active_sorted = sorted(
        [q for q in questions if q.get("is_active")],
        key=lambda x: (int(x.get("sort_order") or 0), int(x.get("id") or 0)),
    )
    if not active_sorted:
        st.caption("No hay preguntas activas para mostrar.")
    else:
        for q in active_sorted:
            qt = question_type_label_es(str(q.get("question_type") or ""))
            ck = SCOPE_LABEL_ES.get(str(q.get("contract_kind") or "tattoo"), "—")
            o = q.get("options")
            extra = ""
            if isinstance(o, list) and o:
                extra = f" — opciones: {', '.join(str(x) for x in o[:5])}{'…' if len(o) > 5 else ''}"
            st.markdown(f"- **{ck}** · **{q.get('label')}** · _{qt}_{extra}")
