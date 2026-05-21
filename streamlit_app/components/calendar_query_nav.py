"""Clic en «Ver cita» / agendar dentro del HTML del calendario → query_params (misma sesión)."""

from __future__ import annotations

import html as html_mod
import json
from urllib.parse import urlencode

import streamlit as st
import streamlit.components.v1 as components


def _query_params_flat() -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        raw = st.query_params.to_dict()
    except AttributeError:
        raw = dict(st.query_params)
    for k, v in raw.items():
        if isinstance(v, list):
            out[str(k)] = str(v[0]) if v else ""
        else:
            out[str(k)] = str(v)
    return out


def calendar_appt_open_href(appt_id: int) -> str:
    qp = _query_params_flat()
    qp.pop("cal_book", None)
    qp["cal_appt_id"] = str(int(appt_id))
    return "?" + urlencode(qp)


def calendar_book_open_href(y: int, m: int, d: int) -> str:
    qp = _query_params_flat()
    qp.pop("cal_appt_id", None)
    qp["cal_book"] = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    return "?" + urlencode(qp)


def calendar_appt_open_control_html(
    appt_id: int,
    *,
    extra_class: str = "",
    monday_iso: str = "",
) -> str:
    """Botón «Ver cita» en la celda; el puente JS fusiona ?cal_appt_id= en la URL."""
    _ = monday_iso
    aid = int(appt_id)
    if aid <= 0:
        return ""
    cls = "cal-appt-slot-link cal-query-nav"
    if extra_class.strip():
        cls += f" {extra_class.strip()}"
    href = html_mod.escape(calendar_appt_open_href(aid), quote=True)
    return (
        f'<button type="button" class="{cls}" '
        f'data-cal-nav="appt" data-cal-appt-id="{aid}" data-cal-href="{href}" '
        f'aria-label="Ver cita">'
        '<span class="cal-appt-slot-link-play" aria-hidden="true">▶</span>'
        "<span>Ver cita</span>"
        "</button>"
    )


def calendar_book_control_html(
    y: int,
    m: int,
    d: int,
    *,
    disabled_footer: bool,
    title_esc: str,
    css_class: str = "cal-footer-book",
) -> str:
    if disabled_footer:
        return (
            f'<span class="{css_class} cal-footer-book--disabled" '
            f'title="{title_esc}" aria-label="{title_esc}">'
            "+ Agregar cita</span>"
        )
    href = html_mod.escape(calendar_book_open_href(y, m, d), quote=True)
    return (
        f'<button type="button" class="{css_class} cal-query-nav" '
        f'data-cal-nav="book" data-cal-y="{int(y)}" data-cal-m="{int(m)}" data-cal-d="{int(d)}" '
        f'data-cal-href="{href}" title="{title_esc}" aria-label="{title_esc}">'
        "+ Agregar cita</button>"
    )


_CAL_NAV_BRIDGE_INNER_JS = r"""
(function () {
  var NS = "__cherryCalNav_v3";

  function appWindow() {
    try {
      return window.top;
    } catch (e0) {
      return window;
    }
  }

  function pad2(n) {
    return n < 10 ? "0" + n : String(n);
  }

  function mergeNavigate(params) {
    var w = appWindow();
    var u = new URL(w.location.href);
    for (var k in params) {
      if (!Object.prototype.hasOwnProperty.call(params, k)) continue;
      if (params[k] == null || params[k] === "") u.searchParams.delete(k);
      else u.searchParams.set(k, String(params[k]));
    }
    w.location.assign(u.toString());
  }

  function navigateFromEl(el) {
    var nav = el.getAttribute("data-cal-nav");
    if (nav === "appt") {
      var apptId = parseInt(el.getAttribute("data-cal-appt-id") || "", 10);
      if (!apptId || apptId <= 0) return;
      mergeNavigate({ cal_appt_id: String(apptId), cal_book: null });
      return;
    }
    if (nav === "book") {
      var cy = parseInt(el.getAttribute("data-cal-y") || "", 10);
      var cm = parseInt(el.getAttribute("data-cal-m") || "", 10);
      var cd = parseInt(el.getAttribute("data-cal-d") || "", 10);
      if (!cd || cd <= 0) return;
      mergeNavigate({
        cal_book: String(cy) + "-" + pad2(cm) + "-" + pad2(cd),
        cal_appt_id: null,
      });
    }
  }

  function onClick(ev) {
    var t = ev.target;
    if (!t || typeof t.closest !== "function") return;
    var el = t.closest(".cal-query-nav,[data-cal-nav]");
    if (!el || el.disabled || el.getAttribute("aria-disabled") === "true") return;
    ev.preventDefault();
    ev.stopPropagation();
    navigateFromEl(el);
  }

  function bindRoot(doc) {
    if (!doc || !doc.body) return;
    var key = NS + "_bound";
    if (doc.documentElement.getAttribute(key)) return;
    doc.documentElement.setAttribute(key, "1");
    doc.addEventListener("click", onClick, true);
  }

  function scanIframes() {
    var w = appWindow();
    var doc = w.document;
    bindRoot(doc);
    var frames = doc.querySelectorAll("iframe");
    for (var i = 0; i < frames.length; i++) {
      try {
        var fdoc = frames[i].contentDocument;
        if (fdoc) bindRoot(fdoc);
      } catch (e) {}
    }
  }

  scanIframes();
  setTimeout(scanIframes, 0);
  setTimeout(scanIframes, 200);
  setTimeout(scanIframes, 600);
  setTimeout(scanIframes, 1500);

  try {
    var w = appWindow();
    var obs = new MutationObserver(function () {
      scanIframes();
    });
    if (w.document && w.document.body) {
      obs.observe(w.document.body, { childList: true, subtree: true });
    }
  } catch (eObs) {}
})();
"""


def _cal_nav_bridge_component_html() -> str:
    inner_lit = json.dumps(_CAL_NAV_BRIDGE_INNER_JS)
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


def inject_calendar_query_nav_bridge() -> None:
    """Puente en documento principal + iframes (`st.html`); patrón login."""
    components.html(_cal_nav_bridge_component_html(), height=0, width=0)


__all__ = [
    "calendar_appt_open_control_html",
    "calendar_appt_open_href",
    "calendar_book_control_html",
    "calendar_book_open_href",
    "inject_calendar_query_nav_bridge",
]
