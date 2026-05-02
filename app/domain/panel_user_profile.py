"""Valores permitidos y etiquetas en español para perfil de usuarios del panel."""
from __future__ import annotations

from typing import Final, Literal

PanelStore = Literal["cherry_tattoo", "rock_city"]
PanelRole = Literal["administrador", "vendedor", "perforador", "tatuador"]

PANEL_STORE_CHOICES: Final[tuple[str, ...]] = ("cherry_tattoo", "rock_city")
PANEL_ROLE_CHOICES: Final[tuple[str, ...]] = ("administrador", "vendedor", "perforador", "tatuador")

PANEL_STORE_LABEL_ES: Final[dict[str, str]] = {
    "cherry_tattoo": "Cherry Tattoo",
    "rock_city": "Rock City",
}

PANEL_ROLE_LABEL_ES: Final[dict[str, str]] = {
    "administrador": "Administrador",
    "vendedor": "Vendedor",
    "perforador": "Perforador",
    "tatuador": "Tatuador",
}
