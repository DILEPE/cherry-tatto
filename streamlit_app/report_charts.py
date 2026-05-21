"""
Gráficas Plotly unificadas para **Reporte** (finanzas y encuestas).
Tema tenue alineado al panel (`main.py`): fondo oscuro, lavanda y rosa acento.

Instalación: `pip install plotly` o `pip install -r requirements.txt`
"""
from __future__ import annotations

from typing import Any, List, Optional, Union

Number = Union[int, float]

from streamlit_app.theme import plotly_theme_dict


def _theme() -> dict[str, str]:
    return plotly_theme_dict()


def plotly_missing_caption() -> str:
    return (
        "Falta **plotly**. Ejecutá en el entorno del proyecto: "
        "`pip install plotly` o `pip install -r requirements.txt`, luego reiniciá Streamlit."
    )


def _import_go() -> Any:
    import plotly.graph_objects as go

    return go


def _base_layout(*, height: int, show_legend: bool = False, margin: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    m = {"l": 56, "r": 28, "t": 36, "b": 80}
    if margin:
        m.update(margin)
    t = _theme()
    return {
        "template": t["template"],
        "paper_bgcolor": t["paper"],
        "plot_bgcolor": t["plot"],
        "font": {"family": t["font_family"], "size": 12, "color": t["text"]},
        "margin": m,
        "height": height,
        "showlegend": show_legend,
    }


def _style_xy_axes(fig: Any, *, x_title: Optional[str], y_title: str) -> None:
    t = _theme()
    title_font = dict(color=t["text"], size=12, family=t["font_family"])
    fig.update_xaxes(
        tickangle=-34,
        automargin=True,
        showgrid=True,
        gridcolor=t["grid"],
        linecolor=t["axis_line"],
        tickfont=dict(color=t["text_muted"], size=11, family=t["font_family"]),
        title=dict(text=x_title if x_title else None, font=title_font),
    )
    fig.update_yaxes(
        automargin=True,
        showgrid=True,
        gridcolor=t["grid"],
        linecolor=t["axis_line"],
        tickfont=dict(color=t["text_muted"], size=11, family=t["font_family"]),
        title=dict(text=y_title, font=title_font),
    )


def render_vertical_bars(
    st: Any,
    *,
    categories: List[str],
    values: List[Number],
    y_title: str,
    x_title: str = "",
    height: Optional[int] = None,
    hovertemplate: Optional[str] = None,
    key: str,
) -> bool:
    """Barras verticales (lavanda + borde rosa, fondo acorde al panel)."""
    try:
        go = _import_go()
    except ImportError:
        st.caption(plotly_missing_caption())
        return False
    if not categories or not values or len(categories) != len(values):
        return False
    t = _theme()
    n = len(categories)
    h = height if height is not None else min(420, 140 + n * 40)
    ht = hovertemplate if hovertemplate is not None else "%{x}<br>%{y}<extra></extra>"
    fig = go.Figure(
        data=[
            go.Bar(
                x=categories,
                y=values,
                marker={
                    "color": t["bar_fill"],
                    "line": {"color": t["bar_line"], "width": 1.8},
                    "opacity": 0.95,
                },
                text=[_bar_outside_text(v) for v in values],
                textposition="outside",
                textfont=dict(color=t["text"], size=11, family=t["font_family"]),
                cliponaxis=False,
                hovertemplate=ht,
            )
        ]
    )
    layout = _base_layout(height=h, show_legend=False)
    fig.update_layout(**layout)
    _style_xy_axes(fig, x_title=x_title or None, y_title=y_title)
    st.plotly_chart(fig, use_container_width=True, key=key)
    return True


def _bar_outside_text(v: Number) -> str:
    if isinstance(v, float):
        if abs(v - round(v)) < 0.01 and v >= 500:
            return f"{int(round(v)):,}".replace(",", ".")
        if v >= 1000:
            return f"{v:,.0f}".replace(",", ".")
        if v == int(v):
            return str(int(v))
        return f"{v:g}"
    if isinstance(v, int) and v >= 1000:
        return f"{v:,}".replace(",", ".")
    return str(v)


def render_pie(
    st: Any,
    *,
    labels: List[str],
    values: List[int],
    height: int = 440,
    key: str,
) -> bool:
    """Torta con % en sectores; leyenda «Convenciones» legible sobre fondo tenue oscuro."""
    try:
        go = _import_go()
    except ImportError:
        st.caption(plotly_missing_caption())
        return False
    if not labels or not values or len(labels) != len(values) or sum(values) <= 0:
        return False
    t = _theme()
    total = float(sum(values))
    legend_labels = [
        f"{lbl}  ·  {100.0 * float(v) / total:.1f}%  ·  n={v}"
        for lbl, v in zip(labels, values)
    ]
    fig = go.Figure(
        data=[
            go.Pie(
                labels=legend_labels,
                values=values,
                hole=0,
                texttemplate="%{percent:.1%}",
                textposition="inside",
                sort=False,
                domain={"x": [0.0, 0.64], "y": [0.06, 0.94]},
                marker={"line": {"color": t["pie_slice_line"], "width": 1.5}},
                textfont={"size": 14, "color": "#ffffff"},
                hovertemplate="<b>%{label}</b><extra></extra>",
            )
        ]
    )
    layout = _base_layout(
        height=height,
        show_legend=True,
        margin={"l": 48, "r": 300, "t": 40, "b": 48},
    )
    layout["legend"] = {
        "title": {
            "text": "Convenciones",
            "font": {
                "size": 15,
                "color": t["text"],
                "family": t["font_family"],
            },
        },
        "orientation": "v",
        "yanchor": "top",
        "y": 1,
        "xanchor": "left",
        "x": 1.02,
        "font": {
            "size": 13,
            "color": t["text"],
            "family": t["font_family"],
        },
        "traceorder": "normal",
        "itemsizing": "constant",
        "itemwidth": 32,
        "valign": "top",
        "bgcolor": t["legend_bg"],
        "bordercolor": t["legend_border"],
        "borderwidth": 1,
    }
    fig.update_layout(**layout)
    st.plotly_chart(fig, use_container_width=True, key=key)
    return True
