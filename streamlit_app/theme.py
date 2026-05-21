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
    out: list[str] = []
    pos = 0
    for match in _THEME_ROOT_RE.finditer(raw):
        out.append(raw[pos : match.start()])
        block_theme = match.group(1)
        brace = raw.find("{", match.end() - 1)
        inner, end = _extract_brace_block(raw, brace)
        if block_theme == theme:
            header = raw[match.start() : brace].strip()
            header = header.replace(
                f':root[data-panel-theme="{theme}"]',
                _ROOT_SELECTOR,
                1,
            )
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
  try {{
    apply(window.parent.document);
  }} catch (e) {{
    apply(document);
  }}
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
      var doc = window.parent && window.parent.document ? window.parent.document : document;
      if (doc && doc.documentElement) {{
        doc.documentElement.setAttribute("data-panel-theme", stored);
        if (doc.body) doc.body.setAttribute("data-panel-theme", stored);
      }}
    }}
  }} catch (e) {{}}
}})();
</script>
"""


def inject_panel_theme(streamlit_module: object) -> None:
    init_panel_theme()
    theme = get_panel_theme()
    markdown = getattr(streamlit_module, "markdown", None)
    if markdown is None:
        raise TypeError("inject_panel_theme requiere el módulo streamlit.")
    panel_css = compile_theme_css(_read_theme_css("_theme_panel.css"), theme)
    wm = build_watermark_css(theme)
    markdown(
        _bootstrap_theme_from_local_storage_script()
        + _theme_dom_sync_script(theme)
        + f"<style>\n{panel_css}\n{wm}\n</style>",
        unsafe_allow_html=True,
    )


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
