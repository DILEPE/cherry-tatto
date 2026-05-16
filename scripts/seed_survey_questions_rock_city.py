#!/usr/bin/env python3
"""
Carga las preguntas de encuesta desde ``scripts/data/survey_questions_seed_rock_city.json``.

Delega en ``seed_survey_questions_from_manifest.py`` (UPSERT en ``survey_questions``).
Solo aplica entradas con ``"is_active": true`` en el JSON, igual que el script genérico.

Requisitos: migraciones ``011``+ y columna ``contract_kind`` (``013``). Variables ``DB_*`` en ``.env``.

Uso (desde la raíz del proyecto)::

    python scripts/seed_survey_questions_rock_city.py
    python scripts/seed_survey_questions_rock_city.py --apply
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ROCK_CITY_MANIFEST = _REPO_ROOT / "scripts/data/survey_questions_seed_rock_city.json"
_GENERIC_SEED = _REPO_ROOT / "scripts/seed_survey_questions_from_manifest.py"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="Ejecutar UPSERT en MySQL.")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo simulación aunque exista --apply.",
    )
    ns = ap.parse_args()

    if not _ROCK_CITY_MANIFEST.is_file():
        print(f"No existe el manifiesto: {_ROCK_CITY_MANIFEST}", file=sys.stderr)
        return 1
    if not _GENERIC_SEED.is_file():
        print(f"No existe el script genérico: {_GENERIC_SEED}", file=sys.stderr)
        return 1

    cmd = [
        sys.executable,
        str(_GENERIC_SEED),
        "--manifest",
        str(_ROCK_CITY_MANIFEST),
    ]
    if ns.apply:
        cmd.append("--apply")
    if ns.dry_run:
        cmd.append("--dry-run")

    return int(subprocess.call(cmd))


if __name__ == "__main__":
    raise SystemExit(main())
