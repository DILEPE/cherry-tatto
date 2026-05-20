"""Vista semanal tipo Outlook/Teams: HTML de rejilla, botones ocultos y bridge JS."""

from __future__ import annotations

import html as html_mod
import json
from datetime import date, timedelta
from typing import Any, Callable

import streamlit as st
import streamlit.components.v1 as components

from streamlit_app.appointment_agenda_slots import duration_slots_for_existing_appointment
from streamlit_app.appointment_dates import appointment_time_hm
from streamlit_app.appointment_slots import time_slot_options
from streamlit_app.appointment_staff_labels import assigned_staff_label
from streamlit_app.components.pills import client_pill_class

__all__ = [
    "WEEK_SCHEDULE_SLOT_PX",
    "inject_week_grid_appt_click_bridge",
    "render_week_grid_hidden_appt_open_buttons",
    "render_week_schedule_grid",
    "twg_sess_appt_open_button_key",
    "week_grid_html_for_week",
    "week_monday",
]


# Altura en px de cada franja de 30 min en la vista semanal tipo Teams/Outlook.
WEEK_SCHEDULE_SLOT_PX = 22


def week_monday(d: date) -> date:
    """Lunes como primer día de la semana (ISO: weekday() 0=lunes)."""
    return d - timedelta(days=d.weekday())


def twg_sess_appt_open_button_key(monday: date, aid: int) -> str:
    """Clave estable para `st.button` oculto que abre una cita desde la rejilla semanal."""
    return f"twg_sess_appt_open_{monday.isoformat()}_{aid}"


def _week_grid_visible_appt_ids(
    monday: date,
    buckets: dict[tuple[int, int, int], list[dict[str, Any]]],
) -> list[int]:
    """IDs de citas visibles en la semana (orden por día y aparición)."""
    out: list[int] = []
    seen: set[int] = set()
    for i in range(7):
        d = monday + timedelta(days=i)
        for row in buckets.get((d.year, d.month, d.day), []):
            aid = int(row.get("id", 0) or 0)
            if aid <= 0 or aid in seen:
                continue
            seen.add(aid)
            out.append(aid)
    return out


def render_week_grid_hidden_appt_open_buttons(
    monday: date,
    buckets: dict[tuple[int, int, int], list[dict[str, Any]]],
) -> None:
    """Botones Streamlit invisibles; el clic en la pastilla HTML delega aquí vía JS (sin navegar por URL)."""
    ids = _week_grid_visible_appt_ids(monday, buckets)
    if not ids:
        return
    keys = [twg_sess_appt_open_button_key(monday, aid) for aid in ids]
    css_chunks = [
        "section.main button."
        + html_mod.escape(f"st-key-{k}")
        + "{position:absolute!important;left:-9999px!important;width:1px!important;"
        "height:1px!important;opacity:0!important;margin:0!important;padding:0!important;}"
        for k in keys
    ]
    st.markdown("<style>" + "\n".join(css_chunks) + "</style>", unsafe_allow_html=True)
    for aid in ids:
        bk = twg_sess_appt_open_button_key(monday, aid)
        if st.button(
            "\u200b",
            key=bk,
            help=f"Abrir cita #{aid} (rejilla semanal)",
            type="tertiary",
            width=1,
        ):
            st.session_state["_cal_focus_appt_id"] = aid
            st.session_state.pop("_cal_overflow_day", None)
            st.rerun()


def inject_week_grid_appt_click_bridge(monday_iso: str) -> None:
    """Engancha clics en `.twg-appt-link` y dispara el `st.button` oculto correspondiente."""
    mon_lit = json.dumps(monday_iso)
    inner_js = f"""
(function () {{
  var NS = "__twgApptOpenBridge_v2";
  var mondayIso = {mon_lit};

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

  function prevTuple(tupleVal) {{
    if (
      !tupleVal ||
      !tupleVal.shell ||
      !tupleVal.onClick ||
      typeof tupleVal.shell.removeEventListener !== "function"
    ) {{
      return;
    }}
    try {{
      tupleVal.shell.removeEventListener("click", tupleVal.onClick, true);
    }} catch (e0) {{}}
  }}

  function mount() {{
    var prev = window[NS];
    if (prev && typeof prev === "object") {{
      prevTuple(prev);
    }}

    function findWidgetButton(doc, aid) {{
      var cls = "st-key-twg_sess_appt_open_" + mondayIso + "_" + aid;
      var esc =
        typeof CSS !== "undefined" && typeof CSS.escape === "function"
          ? CSS.escape(cls)
          : cls;
      try {{
        var hosts = doc.querySelectorAll("." + esc);
        for (var i = 0; i < hosts.length; i++) {{
          var h = hosts[i];
          var btn = h.tagName === "BUTTON" ? h : h.querySelector("button");
          if (btn) return btn;
        }}
      }} catch (e1) {{}}
      return null;
    }}

    function onClick(ev) {{
      var t = ev.target;
      if (!t || typeof t.closest !== "function") return;
      var pill = t.closest("button.twg-appt-link[data-cal-appt-id]");
      if (!pill) return;
      var raw = pill.getAttribute("data-cal-appt-id");
      if (!raw) return;
      ev.preventDefault();
      ev.stopPropagation();
      var aid = parseInt(raw, 10);
      if (!aid || aid <= 0) return;
      var doc = appDocument();
      var wb = findWidgetButton(doc, aid);
      if (wb) {{
        try {{
          wb.click();
        }} catch (e2) {{}}
      }}
    }}

    function bind() {{
      var doc = appDocument();
      var shell = doc.querySelector(".twg-shell");
      if (!shell) return;
      shell.removeEventListener("click", onClick, true);
      shell.addEventListener("click", onClick, true);
      window[NS] = {{ mondayIso: mondayIso, shell: shell, onClick: onClick }};
    }}

    bind();
    setTimeout(bind, 0);
    setTimeout(bind, 120);
    setTimeout(bind, 400);
  }}

  mount();
}})();
"""
    outer = (
        "<script>\n"
        "(function () {\n"
        '  function appDocument() {\n'
        "    try {\n"
        '      var t = window.top;\n'
        '      if (t && t.document && t.document.querySelector(\'[data-testid="stApp"]\')) return t.document;\n'
        "    } catch (e0) {}\n"
        "    var x = window;\n"
        "    for (var i = 0; i < 12; i++) {\n"
        "      try {\n"
        "        if (!x || !x.document) break;\n"
        "        var d = x.document;\n"
        '        if (d.querySelector(\'[data-testid="stApp"]\')) return d;\n'
        "        if (x.parent === x) break;\n"
        "        x = x.parent;\n"
        "      } catch (e) {\n"
        "        break;\n"
        "      }\n"
        "    }\n"
        "    try {\n"
        "      return window.top.document;\n"
        "    } catch (e2) {\n"
        "      return document;\n"
        "    }\n"
        "  }\n"
        "  function injectScript(doc, text) {\n"
        "    try {\n"
        '      var s = doc.createElement("script");\n'
        "      s.textContent = text;\n"
        "      (doc.head || doc.documentElement).appendChild(s);\n"
        "      s.remove();\n"
        "    } catch (e) {}\n"
        "  }\n"
        f"  injectScript(appDocument(), {json.dumps(inner_js)});\n"
        "})();\n"
        "</script>"
    )
    components.html(outer, height=0, width=0)


def week_grid_parse_segments(
    day_rows: list[dict[str, Any]],
    slot_list: list[str],
) -> list[tuple[dict[str, Any], int, int]]:
    """Citas posicionables en la rejilla: (row, start_idx, dur_slots_vis)."""
    n = len(slot_list)
    raw: list[tuple[dict[str, Any], int, int]] = []
    for row in day_rows:
        hm = appointment_time_hm(row.get("appointment_date", row.get("date")))
        if hm == "—":
            continue
        try:
            start_idx = slot_list.index(hm)
        except ValueError:
            continue
        dur = duration_slots_for_existing_appointment(row)
        end_idx = min(start_idx + dur, n)
        vis = max(0, end_idx - start_idx)
        if vis <= 0:
            continue
        raw.append((row, start_idx, vis))
    raw.sort(key=lambda x: (x[1], -x[2]))
    return raw


def week_grid_assign_lanes(
    raw: list[tuple[dict[str, Any], int, int]],
) -> list[tuple[dict[str, Any], int, int, int, int]]:
    """Asigna carril para solapes (greedy). Devuelve (row, start_idx, vis, lane_i, n_lanes)."""
    lanes_end: list[int] = []
    assignments: list[tuple[dict[str, Any], int, int, int]] = []
    for row, start_idx, vis in raw:
        end_idx = start_idx + vis
        lane_i = -1
        for li, le in enumerate(lanes_end):
            if start_idx >= le:
                lane_i = li
                lanes_end[li] = end_idx
                break
        if lane_i < 0:
            lane_i = len(lanes_end)
            lanes_end.append(end_idx)
        assignments.append((row, start_idx, vis, lane_i))
    n_lanes = max(1, len(lanes_end))
    return [(r, s, v, l, n_lanes) for r, s, v, l in assignments]


def week_grid_day_column_html(
    d: date,
    buckets: dict[tuple[int, int, int], list[dict[str, Any]]],
    counts_by_client: dict[str, int],
    *,
    slot_list: list[str],
    slot_px: int,
    today: date,
) -> str:
    """Columna de un día con líneas de tiempo y bloques absolutos."""
    n_slots = len(slot_list)
    total_h = n_slots * slot_px
    day_rows = list(buckets.get((d.year, d.month, d.day), []))
    raw_seg = week_grid_parse_segments(day_rows, slot_list)
    placed = week_grid_assign_lanes(raw_seg)
    today_cls = " twg-col-today" if d == today else ""
    parts: list[str] = [f'<div class="twg-col{today_cls}" style="height:{total_h}px">']
    for si in range(n_slots):
        parts.append(
            f'<div class="twg-slot-line" style="top:{si * slot_px}px;height:{slot_px}px"></div>'
        )
    for row, start_idx, vis, lane_i, n_lanes in placed:
        cls_pill = client_pill_class(row, counts_by_client)
        top = start_idx * slot_px
        height = max(vis * slot_px - 2, 14)
        pct_w = 100.0 / n_lanes
        left = lane_i * pct_w
        nm = str(row.get("customer_name") or row.get("name") or "").strip() or "—"
        nm_esc = html_mod.escape(nm)
        hm = appointment_time_hm(row.get("appointment_date", row.get("date")))
        staff = assigned_staff_label(row)
        tit = html_mod.escape(f"{hm} · {nm}" + (f" · {staff}" if staff != "—" else ""))
        st_cl = str(row.get("status") or "").strip().lower()
        soft_cls = " twg-cancelada-soft" if st_cl == "cancelada" else ""
        ap_id = int(row.get("id", 0) or 0)
        compact = vis <= 1
        link_html = ""
        if ap_id > 0:
            if compact:
                link_html = (
                    f'<button type="button" class="twg-appt-link twg-appt-link--compact" '
                    f'data-cal-appt-id="{ap_id}" aria-label="Ver cita">'
                    '<span class="twg-appt-link-play" aria-hidden="true">▶</span>'
                    "</button>"
                )
            else:
                link_html = (
                    f'<button type="button" class="twg-appt-link" data-cal-appt-id="{ap_id}" '
                    'aria-label="Ver cita">'
                    '<span class="twg-appt-link-play" aria-hidden="true">▶</span>'
                    "<span>Ver cita</span>"
                    "</button>"
                )
        cls_appt_extra = " twg-appt--compact" if compact else ""
        if compact:
            body = (
                f'<span class="twg-appt-time-compact">{html_mod.escape(hm)}</span>'
                f'<span class="twg-appt-client-compact">{nm_esc}</span>'
            )
        else:
            body = (
                '<div class="twg-appt-body-stack">'
                f'<span class="twg-appt-head-time">{html_mod.escape(hm)}</span>'
                f'<span class="twg-appt-client">{nm_esc}</span>'
                "</div>"
            )
        geo = (
            f"top:{top}px;height:{height}px;left:{left}%;width:calc({pct_w}% - 3px);margin-left:1px"
        )
        parts.append(
            f'<div class="twg-appt twg-{cls_pill}{cls_appt_extra}{soft_cls}" '
            f'title="{tit}" style="{geo}">{body}{link_html}</div>'
        )
    parts.append("</div>")
    return "".join(parts)


def week_grid_html_for_week(
    monday: date,
    buckets: dict[tuple[int, int, int], list[dict[str, Any]]],
    counts_by_client: dict[str, int],
    *,
    slot_list: list[str],
    slot_px: int,
) -> str:
    """HTML de la rejilla semanal completa (cabecera + cuerpo)."""
    today = date.today()
    weekdays_short = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    parts: list[str] = ['<div class="twg-shell"><div class="twg-scroll-x"><div class="twg-grid-wrap">']

    parts.append('<div class="twg-head">')
    parts.append('<div class="twg-h-spacer"></div>')
    parts.append('<div class="twg-h-days">')
    for i in range(7):
        d = monday + timedelta(days=i)
        today_cls = " twg-h-today" if d == today else ""
        parts.append(
            f'<div class="twg-h-day{today_cls}"><div class="twg-h-wd">{weekdays_short[i]}</div>'
            f'<div class="twg-h-num">{d.day}</div></div>'
        )
    parts.append("</div></div>")

    parts.append('<div class="twg-body">')
    parts.append('<div class="twg-times">')
    for hm in slot_list:
        is_hour = hm.endswith(":00")
        cls = "twg-tick-major" if is_hour else "twg-tick-minor"
        label = hm if is_hour else ""
        parts.append(f'<div class="twg-tick {cls}" style="height:{slot_px}px"><span>{label}</span></div>')
    parts.append("</div>")
    parts.append('<div class="twg-day-columns">')
    for i in range(7):
        d = monday + timedelta(days=i)
        parts.append(
            week_grid_day_column_html(
                d,
                buckets,
                counts_by_client,
                slot_list=slot_list,
                slot_px=slot_px,
                today=today,
            )
        )
    parts.append("</div></div>")
    parts.append("</div></div></div>")
    return "".join(parts)


def render_week_schedule_grid(
    buckets: dict[tuple[int, int, int], list[dict[str, Any]]],
    counts_by_client: dict[str, int],
    *,
    clear_calendar_dialog_focus: Callable[[], None],
    pop_booking_document_session: Callable[[], None],
    panel_is_technician_role: Callable[[], bool],
) -> None:
    """Vista semanal con columnas por día y bloques proporcionales a la duración (30 min/slot)."""
    anchor_key = "_ap_week_monday"
    if anchor_key not in st.session_state:
        st.session_state[anchor_key] = week_monday(date.today()).isoformat()
    try:
        monday = date.fromisoformat(str(st.session_state[anchor_key]))
    except ValueError:
        monday = week_monday(date.today())
        st.session_state[anchor_key] = monday.isoformat()

    st.markdown("##### Agenda semanal (rejilla horaria)")
    st.caption(
        "Estilo **Outlook / Teams**: columnas por día, franjas de **30 min** (**08:00–20:00**). "
        "En cada bloque, **Ver cita** (▶) abre el detalle en un **panel emergente** sin cambiar de página; "
        "también puedes usar **Lista** para ver todas las citas del día."
    )

    b1, b2, b3, b4 = st.columns([1.1, 1.1, 3.2, 1.1])
    with b1:
        if st.button("◀ Semana", key="twg_prev_week"):
            clear_calendar_dialog_focus()
            st.session_state[anchor_key] = (monday - timedelta(days=7)).isoformat()
            st.rerun()
    with b2:
        if st.button("Hoy", key="twg_today_week"):
            clear_calendar_dialog_focus()
            st.session_state[anchor_key] = week_monday(date.today()).isoformat()
            st.rerun()
    with b3:
        sunday = monday + timedelta(days=6)
        span_lbl = f"{monday.strftime('%d/%m')} – {sunday.strftime('%d/%m/%Y')}"
        st.markdown(
            f"<div style='text-align:center;font-weight:600;padding-top:0.35rem'>{html_mod.escape(span_lbl)}</div>",
            unsafe_allow_html=True,
        )
    with b4:
        if st.button("Semana ▶", key="twg_next_week"):
            clear_calendar_dialog_focus()
            st.session_state[anchor_key] = (monday + timedelta(days=7)).isoformat()
            st.rerun()

    slot_list = time_slot_options()
    st.markdown(
        week_grid_html_for_week(
            monday,
            buckets,
            counts_by_client,
            slot_list=slot_list,
            slot_px=WEEK_SCHEDULE_SLOT_PX,
        ),
        unsafe_allow_html=True,
    )
    render_week_grid_hidden_appt_open_buttons(monday, buckets)
    inject_week_grid_appt_click_bridge(monday.isoformat())

    st.markdown("**Acciones por día**")
    wd_short = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    cols = st.columns(7)
    allow_book = not panel_is_technician_role()
    for i in range(7):
        d = monday + timedelta(days=i)
        day_rows = list(buckets.get((d.year, d.month, d.day), []))
        with cols[i]:
            st.caption(f"{wd_short[i]} **{d.day}** · {len(day_rows)} cita(s)")
            if st.button(
                "Lista",
                key=f"twg_day_list_{d.isoformat()}",
                use_container_width=True,
                disabled=len(day_rows) == 0,
                help="Ver todas las citas del día en un solo panel",
            ):
                st.session_state.pop("_cal_focus_appt_id", None)
                st.session_state["_cal_overflow_day"] = (d.year, d.month, d.day)
                st.rerun()
            past = d < date.today()
            if st.button(
                "Agendar",
                key=f"twg_day_book_{d.isoformat()}",
                use_container_width=True,
                disabled=past or not allow_book,
                help=(
                    "Los tatuadores y perforadores no pueden agendar desde aquí"
                    if not allow_book
                    else ("No se pueden agendar fechas pasadas" if past else "Nueva cita en este día")
                ),
            ):
                clear_calendar_dialog_focus()
                pop_booking_document_session()
                st.session_state["ap_ad"] = d
                st.session_state["_ap_dlg"] = "create"
                st.rerun()
