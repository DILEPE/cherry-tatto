"""Pie del mes (HTML + delegación a botones ocultos) para agendar desde el calendario."""

from __future__ import annotations

import html as html_mod
import json
from datetime import date
from typing import Any, Callable

import streamlit as st
import streamlit.components.v1 as components


def cal_month_appt_open_button_key(appt_id: int) -> str:
    return f"cal_month_appt_open_{int(appt_id)}"


def _month_visible_appt_ids(buckets: dict[tuple[int, int, int], list[dict[str, Any]]]) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()
    for rows in buckets.values():
        for row in rows:
            aid = int(row.get("id", 0) or 0)
            if aid <= 0 or aid in seen:
                continue
            seen.add(aid)
            out.append(aid)
    return out


def calendar_month_footer_strip_html(
    y: int,
    m: int,
    d: int,
    *,
    disabled_footer: bool,
    title_esc: str,
) -> str:
    """Pie de celda mensual tipo cabecera: día visible + botón HTML que delega en `st.button` oculto."""
    strip_cls = "cal-cell-footer-strip"
    if disabled_footer:
        strip_cls += " cal-footer-strip-disabled"
    bd = " disabled" if disabled_footer else ""
    return (
        f'<div class="{strip_cls}" role="presentation">'
        f'<span class="cal-footer-daynum">{html_mod.escape(str(d))}</span>'
        f'<button type="button" class="cal-footer-book" '
        f'data-cal-y="{int(y)}" data-cal-m="{int(m)}" data-cal-d="{int(d)}" '
        f'title="{title_esc}" aria-label="{title_esc}"{bd}>'
        "+ Agregar cita</button>"
        "</div>"
    )


def render_calendar_month_hidden_book_widgets(
    y: int,
    m: int,
    weeks_grid: list[list[int]],
    *,
    panel_is_technician_role: Callable[[], bool],
    clear_calendar_dialog_focus: Callable[[], None],
    pop_booking_document_session: Callable[[], None],
) -> None:
    """Botones ocultos (uno por día) para poder agendar desde el pie HTML mediante JS."""
    allow_book_role = not panel_is_technician_role()
    booked: list[int] = []
    for row in weeks_grid:
        for d in row:
            if d > 0:
                booked.append(d)
    if not booked:
        return
    css_chunks = [
        'section.main button[data-testid^="baseButton"][class*="cal_main_day_"] '
        "{position:absolute!important;left:-9999px!important;width:1px!important;"
        "height:1px!important;opacity:0!important;margin:0!important;padding:0!important;}",
        'section.main div[data-testid="element-container"]:has(button[class*="cal_main_day_"]) '
        "{min-height:0!important;max-height:0!important;margin:0!important;padding:0!important;"
        "border:none!important;overflow:hidden!important;}",
        'section.main div[data-testid="stHorizontalBlock"]:has(button[class*="cal_main_day_"]) '
        "{min-height:0!important;margin:0!important;padding:0!important;gap:0!important;}",
        'section.main div[data-testid="stHorizontalBlock"]:has(button[class*="cal_main_day_"]) '
        '> div[data-testid="column"] {min-height:0!important;padding:0!important;flex:0 0 auto!important;}',
        'section.main div[data-testid="stVerticalBlock"]:has(div[data-testid="stHorizontalBlock"] button[class*="cal_main_day_"]) '
        "{gap:0!important;}",
    ]
    st.markdown("<style>" + "\n".join(css_chunks) + "</style>", unsafe_allow_html=True)
    today_d = date.today()
    chunk = 7
    for i in range(0, len(booked), chunk):
        row_days = booked[i : i + chunk]
        row_cols = st.columns(len(row_days), gap=None)
        for ci, d in enumerate(row_days):
            with row_cols[ci]:
                picked_cell = date(y, m, d)
                bk = f"cal_main_day_{y}_{m}_{d}"
                is_past = picked_cell < today_d
                disabled = is_past or not allow_book_role
                book_help = (
                    "Los tatuadores y perforadores no pueden agendar desde el calendario"
                    if not allow_book_role
                    else (
                        "No se pueden agendar citas en fechas pasadas"
                        if is_past
                        else f"Agendar cita · {picked_cell.strftime('%d/%m/%Y')}"
                    )
                )
                if st.button(
                    "\u200b",
                    key=bk,
                    type="tertiary",
                    width=1,
                    disabled=disabled,
                    help=book_help,
                ):
                    clear_calendar_dialog_focus()
                    pop_booking_document_session()
                    st.session_state["ap_ad"] = date(y, m, d)
                    st.session_state["_ap_dlg"] = "create"
                    st.rerun()


def inject_calendar_month_footer_bridge() -> None:
    """Clicks en `.cal-footer-book` disparan el `st.button` oculto `cal_main_day_…`."""
    inner_js = """
(function () {
  var NS = "__calFooterBook_v1";

  function appDocument() {
    try {
      var t = window.top;
      if (t && t.document && t.document.querySelector('[data-testid="stApp"]')) return t.document;
    } catch (e0) {}
    var x = window;
    for (var i = 0; i < 12; i++) {
      try {
        if (!x || !x.document) break;
        var d = x.document;
        if (d.querySelector('[data-testid="stApp"]')) return d;
        if (x.parent === x) break;
        x = x.parent;
      } catch (e) {
        break;
      }
    }
    try {
      return window.top.document;
    } catch (e2) {
      return document;
    }
  }

  function prevTuple(tupleVal) {
    if (!tupleVal || !tupleVal.shell || !tupleVal.onClick) return;
    try {
      tupleVal.shell.removeEventListener("click", tupleVal.onClick, true);
    } catch (e0) {}
  }

  function mount() {
    var prev = window[NS];
    if (prev && typeof prev === "object") prevTuple(prev);

    function findBookButton(doc, yy, mm, dd) {
      /* Misma convención que la rejilla semanal (clase st-key- + subKey) */
      var subKey = "cal_main_day_" + yy + "_" + mm + "_" + dd;
      var candidates = ["st-key-" + subKey, subKey];
      for (var c = 0; c < candidates.length; c++) {
        var cls = candidates[c];
        var esc =
          typeof CSS !== "undefined" && typeof CSS.escape === "function"
            ? CSS.escape(cls)
            : cls;
        try {
          var hosts = doc.querySelectorAll("." + esc);
          for (var i = 0; i < hosts.length; i++) {
            var h = hosts[i];
            var btn =
              h.tagName === "BUTTON"
                ? h
                : h.querySelector('button[data-testid^="baseButton"]') || h.querySelector("button");
            if (btn && !btn.disabled) return btn;
          }
        } catch (eCls) {}
      }
      try {
        var hits = doc.querySelectorAll('[class*="' + subKey + '"]');
        for (var j = 0; j < hits.length; j++) {
          var node = hits[j];
          var btn =
            node.tagName === "BUTTON"
              ? node
              : node.querySelector('button[data-testid^="baseButton"]');
          if (btn && !btn.disabled) return btn;
        }
      } catch (eSub) {}
      return null;
    }

    function onClick(ev) {
      var t = ev.target;
      if (!t || typeof t.closest !== "function") return;
      var el = t.closest("button.cal-footer-book");
      if (!el || el.closest(".cal-footer-strip-disabled")) return;
      if (el.disabled) return;
      ev.preventDefault();
      ev.stopPropagation();
      var cy = parseInt(el.getAttribute("data-cal-y") || "", 10);
      var cm = parseInt(el.getAttribute("data-cal-m") || "", 10);
      var cd = parseInt(el.getAttribute("data-cal-d") || "", 10);
      if (!cd || cd <= 0) return;
      var doc = appDocument();
      var wb = findBookButton(doc, cy, cm, cd);
      if (wb) {
        try {
          wb.click();
        } catch (e2) {
          try {
            wb.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
          } catch (e3) {}
        }
      }
    }

    function bind() {
      var doc = appDocument();
      var shell =
        doc.querySelector('[data-testid="stMain"]') ||
        doc.querySelector("section.main") ||
        doc.body;
      if (!shell) return;
      shell.removeEventListener("click", onClick, true);
      shell.addEventListener("click", onClick, true);
      window[NS] = { shell: shell, onClick: onClick };
    }

    bind();
    setTimeout(bind, 0);
    setTimeout(bind, 120);
    setTimeout(bind, 400);
  }

  mount();
})();
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


def render_calendar_month_hidden_appt_open_buttons(
    buckets: dict[tuple[int, int, int], list[dict[str, Any]]],
    *,
    clear_calendar_dialog_focus: Callable[[], None],
) -> None:
    """Botones ocultos: clic en «Ver cita» de la celda mensual abre la ficha."""
    ids = _month_visible_appt_ids(buckets)
    if not ids:
        return
    keys = [cal_month_appt_open_button_key(aid) for aid in ids]
    css_chunks = [
        "section.main button."
        + html_mod.escape(f"st-key-{k}")
        + "{position:absolute!important;left:-9999px!important;width:1px!important;"
        "height:1px!important;opacity:0!important;margin:0!important;padding:0!important;}"
        for k in keys
    ]
    st.markdown("<style>" + "\n".join(css_chunks) + "</style>", unsafe_allow_html=True)
    for aid in ids:
        bk = cal_month_appt_open_button_key(aid)
        if st.button(
            "\u200b",
            key=bk,
            help=f"Abrir cita #{aid} (calendario mes)",
            type="tertiary",
            width=1,
        ):
            clear_calendar_dialog_focus()
            st.session_state["_cal_focus_appt_id"] = aid
            st.session_state.pop("_cal_overflow_day", None)
            st.rerun()


def inject_calendar_month_appt_click_bridge() -> None:
    """Clic en `.cal-appt-slot-link` dispara el botón oculto `cal_month_appt_open_*`."""
    inner_js = """
(function () {
  var NS = "__calMonthApptOpenBridge_v1";

  function appDocument() {
    try {
      var t = window.top;
      if (t && t.document && t.document.querySelector('[data-testid="stApp"]')) return t.document;
    } catch (e0) {}
    var x = window;
    for (var i = 0; i < 12; i++) {
      try {
        if (!x || !x.document) break;
        var d = x.document;
        if (d.querySelector('[data-testid="stApp"]')) return d;
        if (x.parent === x) break;
        x = x.parent;
      } catch (e) {
        break;
      }
    }
    try {
      return window.top.document;
    } catch (e2) {
      return document;
    }
  }

  function prevTuple(tupleVal) {
    if (!tupleVal || !tupleVal.shell || !tupleVal.onClick) return;
    try {
      tupleVal.shell.removeEventListener("click", tupleVal.onClick, true);
    } catch (e0) {}
  }

  function mount() {
    var prev = window[NS];
    if (prev && typeof prev === "object") prevTuple(prev);

    function findApptButton(doc, apptId) {
      var subKey = "cal_month_appt_open_" + apptId;
      var candidates = ["st-key-" + subKey, subKey];
      for (var c = 0; c < candidates.length; c++) {
        var cls = candidates[c];
        var esc =
          typeof CSS !== "undefined" && typeof CSS.escape === "function"
            ? CSS.escape(cls)
            : cls;
        try {
          var hosts = doc.querySelectorAll("." + esc);
          for (var i = 0; i < hosts.length; i++) {
            var h = hosts[i];
            var btn =
              h.tagName === "BUTTON"
                ? h
                : h.querySelector('button[data-testid^="baseButton"]') || h.querySelector("button");
            if (btn && !btn.disabled) return btn;
          }
        } catch (eCls) {}
      }
      return null;
    }

    function onClick(ev) {
      var t = ev.target;
      if (!t || typeof t.closest !== "function") return;
      var pill = t.closest("button.cal-appt-slot-link[data-cal-appt-id]");
      if (!pill) return;
      var raw = pill.getAttribute("data-cal-appt-id");
      var apptId = parseInt(raw || "", 10);
      if (!apptId || apptId <= 0) return;
      ev.preventDefault();
      ev.stopPropagation();
      var wb = findApptButton(appDocument(), apptId);
      if (wb) {
        try {
          wb.click();
        } catch (e2) {
          try {
            wb.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
          } catch (e3) {}
        }
      }
    }

    function bind() {
      var doc = appDocument();
      var shell =
        doc.querySelector('[data-testid="stMain"]') ||
        doc.querySelector("section.main") ||
        doc.body;
      if (!shell) return;
      shell.removeEventListener("click", onClick, true);
      shell.addEventListener("click", onClick, true);
      window[NS] = { shell: shell, onClick: onClick };
    }

    bind();
    setTimeout(bind, 0);
    setTimeout(bind, 120);
    setTimeout(bind, 400);
  }

  mount();
})();
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


__all__ = [
    "cal_month_appt_open_button_key",
    "calendar_month_footer_strip_html",
    "inject_calendar_month_appt_click_bridge",
    "inject_calendar_month_footer_bridge",
    "render_calendar_month_hidden_appt_open_buttons",
    "render_calendar_month_hidden_book_widgets",
]
