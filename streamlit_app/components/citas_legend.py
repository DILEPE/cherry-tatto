"""Leyenda de colores del tab Citas."""

from __future__ import annotations

import html as html_mod

import streamlit as st


def render_citas_color_legend() -> None:
    """Franja horizontal: chip de color + texto (misma paleta que las pastillas del calendario)."""
    chips: tuple[tuple[str, str], ...] = (
        ("cli-pill-returning", "Activa cliente antiguo"),
        ("cli-pill-new", "Activa cliente nuevo"),
        ("cli-pill-priority", "Con prioridad"),
        ("cli-pill-reprogramada", "Para reprogramar"),
        ("cli-pill-cancelada", "Cancelada"),
        ("cita-legend-swatch-disponible", "Disponible"),
    )
    parts: list[str] = ['<div class="cita-legend-strip" role="group" aria-label="Leyenda de colores">']
    for cls, label in chips:
        parts.append('<span class="cita-legend-item">')
        parts.append(f'<span class="cita-legend-swatch {html_mod.escape(cls)}" aria-hidden="true"></span>')
        parts.append(f'<span class="cita-legend-label">{html_mod.escape(label)}</span>')
        parts.append("</span>")
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


__all__ = ["render_citas_color_legend"]
