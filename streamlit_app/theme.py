"""
Tema claro/oscuro del panel Streamlit.

- Selector **Apariencia** solo en la barra lateral (usuario autenticado).
- Persistencia en disco (`.streamlit/panel_theme_mode`) y localStorage del navegador.
- En login se aplica el último tema guardado, sin mostrar el selector.
"""
from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Final, Literal

PanelThemeMode = Literal["light", "dark"]

_KEY_THEME: Final[str] = "_panel_theme_mode"
_DEFAULT_THEME: Final[PanelThemeMode] = "dark"
_LS_KEY: Final[str] = "cherry_panel_theme_mode"
_ROOT_SELECTOR = ':root, [data-testid="stAppViewContainer"]'

_WATERMARK_CANDIDATES = (
    Path(__file__).resolve().parent / "assets" / "rock_city_watermark.png",
    Path(__file__).resolve().parent.parent / "assets" / "rock_city_watermark.png",
)
_WATERMARK_STYLE_CACHE: tuple[float, str, PanelThemeMode] | None = None

_THEME_ROOT_RE = re.compile(
    r':root\[data-panel-theme="(light|dark)"\]\s*\{',
    re.MULTILINE,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _theme_pref_path() -> Path:
    return _repo_root() / ".streamlit" / "panel_theme_mode"


def load_persisted_theme() -> PanelThemeMode:
    """Último tema elegido en el panel (sobrevive reinicios de Streamlit)."""
    try:
        raw = _theme_pref_path().read_text(encoding="utf-8").strip().lower()
    except OSError:
        return _DEFAULT_THEME
    return "light" if raw == "light" else "dark"


def save_persisted_theme(mode: PanelThemeMode) -> None:
    path = _theme_pref_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(mode, encoding="utf-8")
    except OSError:
        pass


def init_panel_theme() -> None:
    """Carga tema guardado si la sesión aún no tiene valor."""
    if _KEY_THEME not in st_session_state():
        st_session_state()[_KEY_THEME] = load_persisted_theme()


def get_panel_theme() -> PanelThemeMode:
    raw = str(st_session_state().get(_KEY_THEME) or load_persisted_theme()).strip().lower()
    return "light" if raw == "light" else "dark"


def st_session_state() -> dict:
    import streamlit as st

    return st.session_state


def _styles_directory() -> Path:
    return Path(__file__).resolve().parent / "styles"


def _read_theme_css(name: str) -> str:
    return (_styles_directory() / name).read_text(encoding="utf-8")


def _join_multiline_theme_selectors(css: str) -> str:
    """Une selectores :root[data-panel-theme] en varias líneas antes de `{`."""
    lines = css.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if ":root[data-panel-theme=" not in line:
            out.append(line)
            i += 1
            continue
        selectors: list[str] = []
        while i < len(lines):
            ln = lines[i]
            if "{" in ln:
                before, _, after = ln.partition("{")
                if ":root[data-panel-theme=" in before:
                    selectors.append(before.strip().rstrip(","))
                out.append(", ".join(selectors) + " {" + after)
                i += 1
                break
            if ":root[data-panel-theme=" in ln:
                selectors.append(ln.strip().rstrip(","))
                i += 1
                continue
            break
        else:
            out.extend(selectors)
    return "\n".join(out)


def _extract_brace_block(css: str, open_brace: int) -> tuple[str, int]:
    depth = 0
    i = open_brace
    while i < len(css):
        ch = css[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return css[open_brace : i + 1], i + 1
        i += 1
    return css[open_brace:], len(css)


def compile_theme_css(raw: str, theme: PanelThemeMode) -> str:
    inactive: PanelThemeMode = "dark" if theme == "light" else "light"
    raw = _join_multiline_theme_selectors(raw)
    out: list[str] = []
    pos = 0
    for match in _THEME_ROOT_RE.finditer(raw):
        out.append(raw[pos : match.start()])
        block_theme = match.group(1)
        brace = raw.find("{", match.end() - 1)
        inner, end = _extract_brace_block(raw, brace)
        if block_theme == theme:
            header = raw[match.start() : brace].strip()
            token = f':root[data-panel-theme="{theme}"]'
            while token in header:
                header = header.replace(token, _ROOT_SELECTOR, 1)
            out.append(f"{header} {inner}")
        pos = end
    out.append(raw[pos:])
    merged = "".join(out)
    lines: list[str] = []
    for line in merged.splitlines():
        if f'data-panel-theme="{inactive}"' in line:
            continue
        if f'data-panel-theme="{theme}"' in line:
            line = line.replace(f':root[data-panel-theme="{theme}"]', ":root")
            line = line.replace(f'html[data-panel-theme="{theme}"]', "html")
        lines.append(line)
    return "\n".join(lines)


def build_watermark_css(theme: PanelThemeMode) -> str:
    global _WATERMARK_STYLE_CACHE
    wm_path = next((p for p in _WATERMARK_CANDIDATES if p.is_file()), None)
    if wm_path is None:
        return ""
    try:
        mtime = wm_path.stat().st_mtime
    except OSError:
        return ""
    if (
        _WATERMARK_STYLE_CACHE is not None
        and _WATERMARK_STYLE_CACHE[0] == mtime
        and _WATERMARK_STYLE_CACHE[2] == theme
    ):
        return _WATERMARK_STYLE_CACHE[1]
    b64 = base64.standard_b64encode(wm_path.read_bytes()).decode("ascii")
    uri = f"url(data:image/png;base64,{b64})"
    if theme == "light":
        opacity = "0.045"
        filt = (
            "drop-shadow(1px 1px 0px rgba(0,0,0,0.06)) "
            "brightness(1.02) contrast(1.02)"
        )
        blend = "multiply"
    else:
        opacity = "0.09"
        filt = (
            "drop-shadow(2px 2px 1px rgba(255,255,255,0.16)) "
            "drop-shadow(-1.5px -1.5px 1px rgba(0,0,0,0.45)) "
            "brightness(1.06) contrast(1.08)"
        )
        blend = "soft-light"
    css = f"""
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
    opacity: {opacity};
    filter: {filt};
    mix-blend-mode: {blend};
}}
"""
    _WATERMARK_STYLE_CACHE = (mtime, css, theme)
    return css


def _theme_dom_sync_script(theme: PanelThemeMode) -> str:
    safe = "light" if theme == "light" else "dark"
    return f"""
<script>
(function () {{
  var t = "{safe}";
  var lsKey = "{_LS_KEY}";
  function apply(doc) {{
    if (!doc || !doc.documentElement) return;
    doc.documentElement.setAttribute("data-panel-theme", t);
    if (doc.body) doc.body.setAttribute("data-panel-theme", t);
  }}
  try {{
    localStorage.setItem(lsKey, t);
  }} catch (e) {{}}
  try {{ apply(document); }} catch (e) {{}}
  try {{
    if (window.parent && window.parent.document && window.parent.document !== document) {{
      apply(window.parent.document);
    }}
  }} catch (e) {{}}
}})();
</script>
"""


def _bootstrap_theme_from_local_storage_script() -> str:
    """Antes del primer rerun con sesión, alinea localStorage con el archivo en servidor."""
    server = load_persisted_theme()
    return f"""
<script>
(function () {{
  var lsKey = "{_LS_KEY}";
  var server = "{server}";
    try {{
    var stored = localStorage.getItem(lsKey);
    if (!stored && server) localStorage.setItem(lsKey, server);
    if (stored === "light" || stored === "dark") {{
      function applyTheme(doc) {{
        if (doc && doc.documentElement) {{
          doc.documentElement.setAttribute("data-panel-theme", stored);
          if (doc.body) doc.body.setAttribute("data-panel-theme", stored);
        }}
      }}
      applyTheme(document);
      try {{
        if (window.parent && window.parent.document && window.parent.document !== document) {{
          applyTheme(window.parent.document);
        }}
      }} catch (e2) {{}}
    }}
  }} catch (e) {{}}
}})();
</script>
"""


def _light_portal_widgets_fix_script() -> str:
    """Select (portal) y alertas con fondos oscuros inline de Streamlit en modo claro."""
    return """
<script>
(function () {
  var pending = null;
  var rafLoop = null;
  function docs() {
    var out = [document];
    try {
      if (window.parent && window.parent.document && window.parent.document !== document) {
        out.push(window.parent.document);
      }
    } catch (e) {}
    return out;
  }
  function isLight(doc) {
    var el = doc && doc.documentElement;
    return el && el.getAttribute("data-panel-theme") === "light";
  }
  function paintOption(el, active) {
    var bg = active ? "#f1f5f9" : "#ffffff";
    var fg = active ? "#0f172a" : "#1e293b";
    el.style.setProperty("background", bg, "important");
    el.style.setProperty("background-color", bg, "important");
    el.style.setProperty("color", fg, "important");
    el.querySelectorAll("*").forEach(function (node) {
      if (node.tagName === "SVG" || node.closest("svg")) return;
      node.style.setProperty("background", "transparent", "important");
      node.style.setProperty("background-color", "transparent", "important");
      node.style.setProperty("color", "inherit", "important");
      node.style.setProperty("box-shadow", "none", "important");
    });
  }
  function fixSelectPopovers(doc) {
    if (!isLight(doc)) return;
    doc.querySelectorAll('[data-baseweb="popover"]').forEach(function (pop) {
      if (pop.querySelector('[data-baseweb="calendar"]')) return;
      pop.style.setProperty("background-color", "#ffffff", "important");
      pop.querySelectorAll("li, [role=option]").forEach(function (el) {
        var active =
          el.hasAttribute("data-highlighted") ||
          el.getAttribute("aria-selected") === "true" ||
          el.matches(":hover");
        paintOption(el, active);
      });
    });
  }
  function fixAlerts(doc) {
    if (!isLight(doc)) return;
    doc.querySelectorAll('[data-testid="stAlert"]').forEach(function (alert) {
      var body =
        alert.querySelector('[data-baseweb="notification"]') || alert.firstElementChild;
      if (!body) return;
      var text = (alert.textContent || "").toLowerCase();
      var palette;
      if (/error|no se pudo|obligatorio|no coincide|no puede/.test(text)) {
        palette = { bg: "#fef2f2", border: "#fecaca", color: "#991b1b" };
      } else if (/recomendado/.test(text)) {
        palette = { bg: "#fffbeb", border: "#fcd34d", color: "#92400e" };
      } else {
        palette = { bg: "#eff6ff", border: "#93c5fd", color: "#1e40af" };
      }
      [alert, body].forEach(function (el) {
        el.style.setProperty("background-color", palette.bg, "important");
        el.style.setProperty("border", "1px solid " + palette.border, "important");
        el.style.setProperty("color", palette.color, "important");
      });
      alert.querySelectorAll("p, span, div, strong").forEach(function (n) {
        n.style.setProperty("color", palette.color, "important");
      });
    });
  }
  function hasSelectPopover() {
    return docs().some(function (doc) {
      return (
        isLight(doc) &&
        doc.querySelector(
          '[data-baseweb="popover"]:not(:has([data-baseweb="calendar"]))'
        )
      );
    });
  }
  function portalLoop() {
    docs().forEach(function (doc) {
      if (!isLight(doc)) return;
      fixSelectPopovers(doc);
      fixAlerts(doc);
    });
    if (hasSelectPopover()) rafLoop = requestAnimationFrame(portalLoop);
    else rafLoop = null;
  }
  function ensurePortalLoop() {
    if (!rafLoop) rafLoop = requestAnimationFrame(portalLoop);
  }
  function run() {
    docs().forEach(function (doc) {
      if (!isLight(doc)) return;
      fixSelectPopovers(doc);
      fixAlerts(doc);
    });
    ensurePortalLoop();
  }
  function schedule() {
    if (pending) return;
    pending = requestAnimationFrame(function () {
      pending = null;
      run();
    });
  }
  function onMutations(mutations) {
    for (var i = 0; i < mutations.length; i++) {
      var m = mutations[i];
      if (m.type === "childList") {
        schedule();
        return;
      }
      if (m.type === "attributes") {
        var t = m.target;
        if (t && t.closest && t.closest('[data-baseweb="popover"]')) {
          schedule();
          return;
        }
      }
    }
  }
  docs().forEach(function (doc) {
    if (!doc.body) return;
    try {
      new MutationObserver(onMutations).observe(doc.body, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ["data-highlighted", "aria-selected", "style"],
      });
    } catch (e) {}
    doc.body.addEventListener("mouseover", schedule, true);
  });
  run();
})();
</script>
"""


def _calendar_portal_fix_script() -> str:
    """Placeholder — calendar fix is embedded inside _panel_light_dialog_fix_script."""
    return ""


def _panel_light_dialog_fix_script() -> str:
    """Diálogos modo claro + calendario BaseWeb (días/meses en español, celdas vacías)."""
    return """
<script>
(function () {
  /* ── Calendario: constantes ── */
  var DAY_MAP = {
    "Su":"Do","Mo":"Lu","Tu":"Ma","We":"Mi","Th":"Ju","Fr":"Vi","Sa":"Sá",
    "Sun":"Do","Mon":"Lu","Tue":"Ma","Wed":"Mi","Thu":"Ju","Fri":"Vi","Sat":"Sá"
  };
  var MONTHS_EN = ["January","February","March","April","May","June",
                   "July","August","September","October","November","December"];
  var MONTHS_ES = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
                   "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"];

  var DIALOG_MARKERS =
    ".dlg-pu-root, [data-pu-dlg], .dlg-store-root, [data-store-dlg], " +
    ".dlg-cust-root, .ctadm-dlg-root, [data-ctadm-dlg], " +
    ".dlg-survey-root, [data-survey-dlg], " +
    ".ap-search-dialog-root, [data-ap-search-dlg]";
  var MIN_QUILL_PX = 420;
  function docs() {
    var out = [document];
    try {
      if (window.parent && window.parent.document && window.parent.document !== document) {
        out.push(window.parent.document);
      }
    } catch (e) {}
    return out;
  }
  function isLight(doc) {
    var el = doc && doc.documentElement;
    return el && el.getAttribute("data-panel-theme") === "light";
  }
  /* ── Calendario: helpers ── */
  function replaceMonthText(root, doc) {
    if (!root) return;
    try {
      var walker = doc.createTreeWalker(root, 4 /* SHOW_TEXT */, null, false);
      var node;
      while ((node = walker.nextNode())) {
        var t = node.textContent.trim();
        var i = MONTHS_EN.indexOf(t);
        if (i >= 0) node.textContent = MONTHS_ES[i];
      }
    } catch (e) {}
  }
  function fixCalendar(doc) {
    var cals = doc.querySelectorAll('[data-baseweb="calendar"]');
    if (!cals.length) return;
    var light = isLight(doc);
    cals.forEach(function (cal) {
      /* Transparent grid containers (both themes). */
      cal.querySelectorAll('[role="grid"],[role="rowgroup"],[role="row"]').forEach(function (el) {
        el.style.setProperty("background", "transparent", "important");
        el.style.setProperty("background-color", "transparent", "important");
      });
      /* Transparent ALL row children — catches empty cells whatever their role. */
      cal.querySelectorAll('[role="row"] > *').forEach(function (cell) {
        if (cell.tagName.toLowerCase() !== "button") {
          cell.style.setProperty("background", "transparent", "important");
          cell.style.setProperty("background-color", "transparent", "important");
        }
      });
      /* Spanish weekday names — targets role="columnheader" AND data-baseweb="calendar-weekday". */
      var seen = [];
      var rawHeaders = cal.querySelectorAll(
        '[role="columnheader"],[data-baseweb="calendar-weekday"]'
      );
      var headers = [];
      for (var h = 0; h < rawHeaders.length; h++) {
        if (seen.indexOf(rawHeaders[h]) === -1) { seen.push(rawHeaders[h]); headers.push(rawHeaders[h]); }
      }
      headers.forEach(function (el) {
        var abbr = el.querySelector("abbr");
        var target = abbr || el;
        var orig = target.textContent.trim();
        var es = DAY_MAP[orig];
        if (es && orig !== es) {
          target.textContent = es;
          if (abbr) abbr.removeAttribute("title");
        }
        el.style.setProperty("font-size", "0.82rem", "important");
        el.style.setProperty("color", light ? "#64748b" : "#94a3b8", "important");
        el.style.setProperty("font-weight", "600", "important");
      });
      /* Spanish month name in header. */
      var hdr = cal.querySelector('header,[data-baseweb="calendar-header"]');
      if (hdr) replaceMonthText(hdr, doc);
      /* Light mode: white popover + calendar surface. */
      if (light) {
        var pop = cal.closest('[data-baseweb="popover"]');
        if (pop) pop.style.setProperty("background-color", "#ffffff", "important");
        cal.style.setProperty("background-color", "#ffffff", "important");
      }
    });
    /* Spanish month names in open month-select listbox. */
    doc.querySelectorAll('[data-baseweb="menu"] [role="option"]').forEach(function (opt) {
      replaceMonthText(opt, doc);
    });
  }
  function paintDialogLight(doc) {
    if (!isLight(doc)) return;
    var grad =
      "linear-gradient(180deg, #ff5fb8 0%, #ff007f 52%, #d90064 100%)";
    doc.querySelectorAll(DIALOG_MARKERS).forEach(function (marker) {
      var dlg = marker.closest('div[data-testid="stDialog"]');
      if (!dlg) return;
      var shell = dlg.querySelector('[role="dialog"]') || dlg;
      shell.style.setProperty("background-color", "#ffffff", "important");
      shell.style.setProperty("color", "#1e293b", "important");
      dlg.querySelectorAll(
        '[data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] label, ' +
          '[data-testid="stCaptionContainer"] p, [data-testid="stMarkdownContainer"] p, ' +
          '[data-testid="stMarkdownContainer"] h5, [data-testid="stMarkdownContainer"] strong'
      ).forEach(function (el) {
        el.style.setProperty("color", "#334155", "important");
      });
      dlg.querySelectorAll(
        '[data-testid="stButton"] button[data-testid="baseButton-primary"], ' +
          '[data-testid="stButton"] button[kind="primary"], ' +
          'button[data-testid="baseButton-primary"][class*="st-emotion-cache"]'
      ).forEach(function (btn) {
        btn.style.setProperty("background-image", grad, "important");
        btn.style.setProperty("background-color", "#ff007f", "important");
        btn.style.setProperty("color", "#ffffff", "important");
        btn.style.setProperty("border", "1px solid rgba(255, 0, 127, 0.35)", "important");
        btn.style.setProperty("box-shadow", "0 4px 14px rgba(255, 0, 127, 0.38)", "important");
        btn.querySelectorAll("*").forEach(function (node) {
          node.style.setProperty("color", "#ffffff", "important");
          node.style.setProperty("background", "transparent", "important");
          node.style.setProperty("background-color", "transparent", "important");
        });
      });
    });
  }
  function fixQuill(doc) {
    doc.querySelectorAll(
      'div[data-testid="stDialog"] [data-testid="stCustomComponentV1"]'
    ).forEach(function (host) {
      var dlg = host.closest('div[data-testid="stDialog"]');
      if (!dlg || !dlg.querySelector(DIALOG_MARKERS)) {
        return;
      }
      host.style.setProperty("width", "100%", "important");
      host.style.setProperty("max-width", "100%", "important");
      var inner = host.firstElementChild;
      if (inner) {
        inner.style.setProperty("width", "100%", "important");
        inner.style.setProperty("max-width", "100%", "important");
      }
      var iframe = host.querySelector("iframe");
      if (!iframe) return;
      var w = host.getBoundingClientRect().width;
      if (w > 48) {
        iframe.style.setProperty("width", w + "px", "important");
      }
      iframe.style.setProperty("min-width", "100%", "important");
      iframe.style.setProperty("display", "block", "important");
      var h = Math.max(MIN_QUILL_PX, parseInt(iframe.style.height, 10) || 0);
      if (h < MIN_QUILL_PX) {
        iframe.style.setProperty("min-height", MIN_QUILL_PX + "px", "important");
        iframe.style.setProperty("height", MIN_QUILL_PX + "px", "important");
      }
    });
  }
  function fixReportMetrics(doc) {
    if (!isLight(doc)) return;
    doc.querySelectorAll(
      '[data-testid="stMain"]:has(.rep-tab-root) [data-testid="stMetric"]'
    ).forEach(function (metric) {
      metric.style.setProperty("background-color", "#ffffff", "important");
      metric.style.setProperty("border", "1px solid rgba(15, 23, 42, 0.12)", "important");
      metric.querySelectorAll(
        '[data-testid="stMetricLabel"] p, [data-testid="stMetricLabel"] div, [data-testid="stMetricLabel"] label'
      ).forEach(function (el) {
        el.style.setProperty("color", "#475569", "important");
      });
      metric.querySelectorAll(
        '[data-testid="stMetricValue"], [data-testid="stMetricValue"] div'
      ).forEach(function (el) {
        el.style.setProperty("color", "#0f172a", "important");
      });
    });
  }
  function run() {
    docs().forEach(function (doc) {
      paintDialogLight(doc);
      fixQuill(doc);
      fixReportMetrics(doc);
      fixCalendar(doc);
    });
  }
  var pending = null;
  function schedule() {
    if (pending) return;
    pending = requestAnimationFrame(function () {
      pending = null;
      run();
    });
  }
  docs().forEach(function (doc) {
    if (!doc.body) return;
    try {
      new MutationObserver(schedule).observe(doc.body, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ["style", "class"],
      });
    } catch (e) {}
    window.addEventListener("resize", schedule);
  });
  run();
  setInterval(run, 350);
})();
</script>
"""


def inject_panel_theme(streamlit_module: object) -> None:
    init_panel_theme()
    theme = get_panel_theme()
    markdown = getattr(streamlit_module, "markdown", None)
    if markdown is None:
        raise TypeError("inject_panel_theme requiere el módulo streamlit.")
    panel_css = compile_theme_css(_read_theme_css("_theme_panel.css"), theme)
    panel_css += "\n" + compile_theme_css(_read_theme_css("_theme_contracts.css"), theme)
    panel_css += "\n" + compile_theme_css(_read_theme_css("_theme_stores.css"), theme)
    panel_css += "\n" + compile_theme_css(_read_theme_css("_theme_panel_users.css"), theme)
    panel_css += "\n" + compile_theme_css(_read_theme_css("_theme_report.css"), theme)
    panel_css += "\n" + compile_theme_css(_read_theme_css("_theme_survey_questions.css"), theme)
    portal_script = _calendar_portal_fix_script() + _panel_light_dialog_fix_script()
    if theme == "light":
        panel_css += "\n" + _read_theme_css("_theme_light_portal_fix.css")
        panel_css += "\n" + compile_theme_css(_read_theme_css("_theme_calendar_light.css"), theme)
        panel_css += "\n" + compile_theme_css(_read_theme_css("_theme_customers.css"), theme)
        portal_script += _light_portal_widgets_fix_script()
    wm = build_watermark_css(theme)
    markdown(
        _bootstrap_theme_from_local_storage_script()
        + _theme_dom_sync_script(theme)
        + portal_script
        + f"<style>\n{panel_css}\n{wm}\n</style>",
        unsafe_allow_html=True,
    )
    _inject_calendar_fix_component(streamlit_module, theme)


def _inject_calendar_fix_component(streamlit_module: object, theme: PanelThemeMode) -> None:
    """Fix del calendario BaseWeb via st.html con unsafe_allow_javascript=True."""
    html_fn = getattr(streamlit_module, "html", None)
    if html_fn is None:
        return
    light_str = "true" if theme == "light" else "false"
    try:
        html_fn(
            f"""<script>
(function(){{
  if(window._chCalDone)return;
  window._chCalDone=true;
  var DAY_MAP={{"Su":"Do","Mo":"Lu","Tu":"Ma","We":"Mi","Th":"Ju","Fr":"Vi","Sa":"Sá",
               "Sun":"Do","Mon":"Lu","Tue":"Ma","Wed":"Mi","Thu":"Ju","Fri":"Vi","Sat":"Sá"}};
  var MEN=["January","February","March","April","May","June","July","August","September","October","November","December"];
  var MES=["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"];
  var light={light_str};
  function replM(root){{
    try{{var w=document.createTreeWalker(root,4,null,false),n;
      while((n=w.nextNode())){{var orig=n.textContent.trim(),i=MEN.indexOf(orig);if(i>=0)n.textContent=MES[i];}}
    }}catch(e){{}}
  }}
  function fix(){{
    var cals=document.querySelectorAll('[data-baseweb="calendar"]');
    if(!cals.length)return;
    cals.forEach(function(cal){{
      cal.querySelectorAll('[role="grid"],[role="rowgroup"],[role="row"]').forEach(function(el){{
        el.style.setProperty("background","transparent","important");
        el.style.setProperty("background-color","transparent","important");
      }});
      cal.querySelectorAll('[role="row"]>*').forEach(function(c){{
        c.style.setProperty("background","transparent","important");
        c.style.setProperty("background-color","transparent","important");
      }});
      var seen=[],raw=cal.querySelectorAll('[role="columnheader"],[data-baseweb="calendar-weekday"]'),hdrs=[];
      for(var i=0;i<raw.length;i++){{if(seen.indexOf(raw[i])===-1){{seen.push(raw[i]);hdrs.push(raw[i]);}}}}
      hdrs.forEach(function(el){{
        var ab=el.querySelector("abbr"),t=ab||el;
        var orig=t.textContent.trim(),es=DAY_MAP[orig];
        if(es&&orig!==es){{t.textContent=es;if(ab)ab.removeAttribute("title");}}
        el.style.setProperty("font-size","0.82rem","important");
        el.style.setProperty("color",light?"#64748b":"#94a3b8","important");
        el.style.setProperty("font-weight","600","important");
      }});
      var hdr=cal.querySelector('header,[data-baseweb="calendar-header"]');
      if(hdr)replM(hdr);
      if(light){{
        var pop=cal.closest('[data-baseweb="popover"]');
        if(pop)pop.style.setProperty("background-color","#ffffff","important");
        cal.style.setProperty("background-color","#ffffff","important");
      }}
    }});
    document.querySelectorAll('[data-baseweb="menu"] [role="option"]').forEach(function(o){{replM(o);}});
  }}
  new MutationObserver(function(ms){{
    for(var i=0;i<ms.length;i++){{if(ms[i].type==="childList"){{fix();return;}}}}
  }}).observe(document.body,{{childList:true,subtree:true}});
  fix();
  setInterval(fix,300);
}})();
</script>""",
            unsafe_allow_javascript=True,
        )
    except Exception:
        pass


def _on_theme_mode_changed() -> None:
    mode = get_panel_theme()
    save_persisted_theme(mode)


def render_theme_mode_control(streamlit_module: object) -> None:
    """Selector Claro / Oscuro (solo barra lateral, usuario dentro del panel)."""
    init_panel_theme()
    radio = getattr(streamlit_module, "radio", None)
    if radio is None:
        return
    radio(
        "Apariencia",
        options=["light", "dark"],
        format_func=lambda t: "Claro" if t == "light" else "Oscuro",
        key=_KEY_THEME,
        horizontal=True,
        label_visibility="visible",
        on_change=_on_theme_mode_changed,
    )


def compile_citas_theme_css(raw: str | None = None) -> str:
    text = raw if raw is not None else _read_theme_css("_theme_citas.css")
    return compile_theme_css(text, get_panel_theme())


def plotly_theme_dict() -> dict[str, str]:
    if get_panel_theme() == "light":
        return {
            "paper": "rgba(255, 255, 255, 0.98)",
            "plot": "rgba(249, 250, 251, 0.99)",
            "text": "#1f2937",
            "text_muted": "#6b7280",
            "grid": "rgba(15, 23, 42, 0.08)",
            "axis_line": "rgba(15, 23, 42, 0.14)",
            "bar_fill": "rgba(167, 154, 255, 0.72)",
            "bar_line": "rgba(255, 0, 127, 0.45)",
            "pie_slice_line": "rgba(255, 255, 255, 0.9)",
            "legend_bg": "rgba(255, 255, 255, 0.96)",
            "legend_border": "rgba(255, 0, 127, 0.28)",
            "font_family": "Inter, system-ui, 'Segoe UI', sans-serif",
            "template": "plotly_white",
        }
    return {
        "paper": "rgba(30, 30, 34, 0.96)",
        "plot": "rgba(22, 22, 26, 0.98)",
        "text": "#eaeaea",
        "text_muted": "#a3a3b0",
        "grid": "rgba(255, 255, 255, 0.07)",
        "axis_line": "rgba(255, 255, 255, 0.14)",
        "bar_fill": "rgba(167, 154, 255, 0.78)",
        "bar_line": "rgba(255, 0, 127, 0.5)",
        "pie_slice_line": "rgba(0, 0, 0, 0.4)",
        "legend_bg": "rgba(30, 30, 34, 0.94)",
        "legend_border": "rgba(167, 154, 255, 0.38)",
        "font_family": "Inter, system-ui, 'Segoe UI', sans-serif",
        "template": "plotly_dark",
    }
