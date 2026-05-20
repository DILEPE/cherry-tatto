"""Elimina de citas_tab.py bloques ya extraídos según RANGES_DESC (líneas 1-based).

IMPORTANTE: actualiza RANGES_DESC tras cada poda; los índices cambian.
Ver scripts/README-citas-tab-refactor.md para el mapa usado en el refactor modular.
"""

from pathlib import Path

TAB = Path(__file__).resolve().parent.parent / "streamlit_app" / "citas_tab.py"
lines = TAB.read_text(encoding="utf-8").splitlines(keepends=True)

# Rangos inclusivos en líneas 1-based; orden descendente por inicio para no romper índices
RANGES_DESC = sorted(
    [
        (2003, 2362),
        (1523, 1971),
        (859, 1324),
        (783, 854),
        (770, 781),
        (686, 713),
        (659, 669),
        (541, 591),
        (510, 516),
        (372, 442),
        (98, 182),
    ],
    key=lambda x: x[0],
    reverse=True,
)

for start, end in RANGES_DESC:
    del lines[start - 1 : end]

TAB.write_text("".join(lines), encoding="utf-8")
print("Pruned citas_tab ranges:", RANGES_DESC)
