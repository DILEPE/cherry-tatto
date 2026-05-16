#!/usr/bin/env python3
"""Genera `app/assets/receipt_rock_city_logo.png` desde el watermark Rock City.

Lee `streamlit_app/assets/rock_city_watermark.png`, compone sobre fondo negro y
remapa píxeles visibles: trazo alto/blanco en inglés, zona inferior (~纹身) en #E53E3E.

Requisito: `pip install pillow` (está en requirements.txt).
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Instala Pillow: pip install pillow", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "streamlit_app" / "assets" / "rock_city_watermark.png"
DST = ROOT / "app" / "assets" / "receipt_rock_city_logo.png"

# Rojo marca alineado con _MARK_RED_UI en payment_receipt_pdf.py (~#E53E3E).
MARK_RED = (229, 62, 62)
# Bajo esta fracción de altura suele ir solo el bloque de caracteres chinos (p. ej. 纹身).
# Ajustar solo si cambias el arte en rock_city_watermark.png.
CHINESE_ZONE_TOP_FRAC = 0.793


def main() -> None:
    if not SRC.is_file():
        print(f"No existe origen: {SRC}", file=sys.stderr)
        sys.exit(1)
    im = Image.open(SRC).convert("RGBA")
    w, h = im.size
    px = im.load()
    out = Image.new("RGB", (w, h), (0, 0, 0))
    op = out.load()
    # El PNG «watermark» suele ser casi todo opaco: fondo gris claro (~247) + trazos oscuros.
    # Sin este corte, todo el lienzo acaba en blanco y en el PDF negro solo se ve un rectángulo blanco.
    bg_lum_cutoff = 218
    chinese_y0 = int(h * CHINESE_ZONE_TOP_FRAC)

    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a < 28:
                continue
            lum = (r + g + b) / 3
            if lum >= bg_lum_cutoff:
                continue
            # Tinte rojo ya presente en el PNG fuente (si lo hubiera).
            if r >= max(g, b) + 22 and r >= 95:
                op[x, y] = MARK_RED
            elif y >= chinese_y0:
                op[x, y] = MARK_RED
            else:
                op[x, y] = (255, 255, 255)
    DST.parent.mkdir(parents=True, exist_ok=True)
    out.save(DST, "PNG")
    print(f"Escrito {DST} ({w}x{h}) desde {SRC}")


if __name__ == "__main__":
    main()
