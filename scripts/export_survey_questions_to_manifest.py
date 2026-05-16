#!/usr/bin/env python3
"""
Exporta todas las filas actuales de `survey_questions` a un JSON compatible con
`backfill_survey_questions_existing.py` y `seed_survey_questions_from_manifest.py`.

Así obtienes en disco **la lista completa** de preguntas que ya tienes en la base.

- En la **misma base**, tras editar el JSON: ``backfill_survey_questions_existing.py --apply``.
- En la **base destino sin preguntas** (tabla vacía): ``seed_survey_questions_from_manifest.py --manifest <archivo> --apply`` (el backfill no insertaría nada).

Requisitos: `.env` con DB_*; migraciones `011`+ y columna `contract_kind` (`013`).

Uso::

    python scripts/export_survey_questions_to_manifest.py
    python scripts/export_survey_questions_to_manifest.py --output scripts/data/mi_encuesta.json
    python scripts/export_survey_questions_to_manifest.py --only-active

Salida: objeto JSON con clave `questions` (array ordenado por sort_order, id).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent

try:
    import mysql.connector
except ImportError:
    print("pip install mysql-connector-python python-dotenv", file=sys.stderr)
    raise

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[misc, assignment]


def _decode_options(raw: Any) -> tuple[Any, bool]:
    """Devuelve (valor para JSON 'options', True si hubo texto no parseable como lista JSON)."""
    if raw is None:
        return None, False
    s = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
    s = s.strip()
    if not s:
        return None, False
    try:
        data = json.loads(s)
        if isinstance(data, list):
            return data, False
        return None, True
    except json.JSONDecodeError:
        return None, True


def main() -> int:
    if load_dotenv:
        load_dotenv()

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--output",
        "-o",
        type=Path,
        default=_REPO_ROOT / "scripts/data/survey_questions_manifest.json",
        help="Ruta del JSON de salida.",
    )
    ap.add_argument(
        "--only-active",
        action="store_true",
        help="Solo preguntas con is_active=1 en la base.",
    )
    ap.add_argument(
        "--stdout",
        action="store_true",
        help="Imprime JSON por salida estándar en lugar de escribir archivo.",
    )
    ns = ap.parse_args()

    host = os.getenv("DB_HOST")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    database = os.getenv("DB_NAME", "cherry_tatto")
    if not host or not user or password is None:
        print("Define DB_HOST, DB_USER, DB_PASSWORD (y opcional DB_NAME) en .env", file=sys.stderr)
        return 1

    conn = mysql.connector.connect(host=host, user=user, password=password, database=database)
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT COUNT(*) AS n FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = 'survey_questions'
              AND column_name = 'contract_kind'
            """
        )
        row = cur.fetchone()
        if not row or int(row["n"]) == 0:
            print("Falta columna contract_kind. Aplica la migración 013.", file=sys.stderr)
            return 1

        q = """
            SELECT id, label, question_type, options_json, sort_order, contract_kind, is_active
            FROM survey_questions
            WHERE 1=1
        """
        if ns.only_active:
            q += " AND is_active = 1"
        q += " ORDER BY sort_order ASC, id ASC"

        cur.execute(q)
        rows = cur.fetchall()

        questions: list[dict[str, Any]] = []
        unparsed_ids: list[int] = []

        for r in rows:
            rid = int(r["id"])
            opts, bad = _decode_options(r.get("options_json"))
            if bad:
                unparsed_ids.append(rid)

            entry: dict[str, Any] = {
                "id": rid,
                "label": str(r.get("label") or ""),
                "question_type": str(r.get("question_type") or ""),
                "options": opts,
                "sort_order": int(r.get("sort_order") or 0),
                "contract_kind": str(r.get("contract_kind") or "tattoo").strip().lower(),
                "is_active": bool(int(r.get("is_active") or 0)),
            }
            questions.append(entry)

        payload = {
            "_generated_by": "scripts/export_survey_questions_to_manifest.py",
            "_note": "Edita 'questions'. Misma BD: backfill_survey_questions_existing.py --apply. BD nueva: seed_survey_questions_from_manifest.py --manifest <este archivo> --apply",
            "questions": questions,
        }

        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

        if unparsed_ids:
            print(
                f"Aviso: options_json no era lista JSON en ids {unparsed_ids}; "
                "se exportó options=null. Revisa esas filas a mano en el JSON o en el panel.",
                file=sys.stderr,
            )

        if ns.stdout:
            sys.stdout.write(text)
            return 0

        out_path = ns.output.expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        print(f"Exportadas {len(questions)} pregunta(s) → {out_path}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
