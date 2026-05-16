#!/usr/bin/env python3
"""
Actualiza **solo preguntas que ya existen** en `survey_questions` (nunca inserta filas).

Útil para alinear texto, tipo, opciones, orden, `contract_kind` e `is_active` con un manifiesto
JSON sin crear IDs nuevos ni pisar la tabla entera con un seed inicial.

Formato del manifiesto (clave `questions`): lista de objetos con `id` obligatorio; mismo esquema que
`scripts/data/survey_questions_manifest.json` y compatible con `seed_survey_questions_from_manifest.py`.

Para **obtener todas las preguntas que ya están en la base** (lista completa editable), exporta primero::

    python scripts/export_survey_questions_to_manifest.py
    python scripts/export_survey_questions_to_manifest.py --only-active -o scripts/data/mi_manifiesto.json

Luego editas el JSON. Para **actualizar solo filas que ya existen** en esa misma base, usa este script
con `--apply`. Para **vaciar o poblar otra base nueva** con los mismos IDs, usa en su lugar
``seed_survey_questions_from_manifest.py --manifest ... --apply``.

Requisitos: migraciones `011`+ y columna `contract_kind` (`013`). Variables `DB_*` en `.env`.

Uso (desde la raíz del proyecto)::

    python scripts/backfill_survey_questions_existing.py
    python scripts/backfill_survey_questions_existing.py --apply
    python scripts/backfill_survey_questions_existing.py --apply --only-ids 3,4

Por defecto solo lista cambios; `--apply` ejecuta UPDATE.
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

_QUESTION_TYPES = frozenset(
    {
        "rating_1_5",
        "yes_no",
        "text",
        "radio",
        "checkbox",
        "select",
        "textarea",
        "text_short",
        "number",
    }
)
_CONTRACT_KINDS = frozenset({"tattoo", "piercing", "both"})


def _load_manifest(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get("questions")
    if not isinstance(raw, list):
        raise ValueError("El manifiesto debe tener una clave 'questions' (lista).")
    return [x for x in raw if isinstance(x, dict)]


def _options_to_db(raw_options: Any) -> str | None:
    if raw_options is None:
        return None
    if isinstance(raw_options, list):
        return json.dumps(raw_options, ensure_ascii=False)
    if isinstance(raw_options, str) and raw_options.strip():
        return raw_options.strip()
    raise ValueError(f"options debe ser lista JSON o texto, recibido: {type(raw_options)!r}")


def _has_contract_kind_column(cursor: Any) -> bool:
    cursor.execute(
        """
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'survey_questions'
          AND column_name = 'contract_kind'
        """
    )
    row = cursor.fetchone()
    return int(row[0]) > 0 if row else False


def main() -> int:
    if load_dotenv:
        load_dotenv()

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--manifest",
        type=Path,
        default=_REPO_ROOT / "scripts/data/survey_questions_manifest.json",
        help="JSON con la lista `questions` (usa `id` para hacer match con la BD).",
    )
    ap.add_argument("--apply", action="store_true", help="Ejecutar UPDATE.")
    ap.add_argument("--dry-run", action="store_true", help="No escribe aunque exista --apply.")
    ap.add_argument(
        "--only-ids",
        type=str,
        default="",
        help="Lista separada por comas de ids del manifiesto a procesar (vacío = todas las del archivo).",
    )
    ns = ap.parse_args()

    manifest_path = ns.manifest.expanduser().resolve()
    if not manifest_path.is_file():
        print(f"No existe el manifiesto: {manifest_path}", file=sys.stderr)
        return 1

    only_ids: set[int] | None = None
    if ns.only_ids.strip():
        only_ids = set()
        for part in ns.only_ids.split(","):
            part = part.strip()
            if part:
                only_ids.add(int(part))

    entries = _load_manifest(manifest_path)
    write_db = bool(ns.apply) and not bool(ns.dry_run)

    host = os.getenv("DB_HOST")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    database = os.getenv("DB_NAME", "cherry_tatto")
    if not host or not user or password is None:
        print("Define DB_HOST, DB_USER, DB_PASSWORD (y opcional DB_NAME) en .env", file=sys.stderr)
        return 1

    conn = mysql.connector.connect(host=host, user=user, password=password, database=database)
    try:
        cur = conn.cursor()
        if not _has_contract_kind_column(cur):
            print(
                "Falta columna contract_kind en survey_questions. Aplica la migración 013.",
                file=sys.stderr,
            )
            return 1

        cur.execute("SELECT id FROM survey_questions")
        existing_ids = {int(r[0]) for r in cur.fetchall()}

        prepared: list[tuple[int, str, str, str | None, int, str, int]] = []
        skipped_absent: list[int] = []

        for e in entries:
            qid = e.get("id")
            if qid is None:
                print("Entrada sin 'id' ignorada.", file=sys.stderr)
                continue
            qid = int(qid)
            if only_ids is not None and qid not in only_ids:
                continue
            if qid not in existing_ids:
                skipped_absent.append(qid)
                continue

            label = str(e.get("label") or "").strip()
            qtype = str(e.get("question_type") or "").strip()
            sort_order = int(e.get("sort_order") or 0)
            ck = str(e.get("contract_kind") or "tattoo").strip().lower()
            is_act = bool(e.get("is_active", True))

            if not label:
                print(f"id={qid}: label obligatorio.", file=sys.stderr)
                return 1
            if qtype not in _QUESTION_TYPES:
                print(f"id={qid}: question_type inválido '{qtype}'.", file=sys.stderr)
                return 1
            if ck not in _CONTRACT_KINDS:
                print(f"id={qid}: contract_kind inválido.", file=sys.stderr)
                return 1

            needs_opts = qtype in ("radio", "checkbox", "select")
            opts_raw = e.get("options")
            if needs_opts and (opts_raw is None or (isinstance(opts_raw, list) and len(opts_raw) == 0)):
                print(f"id={qid}: '{qtype}' requiere options no vacío.", file=sys.stderr)
                return 1

            oj: str | None
            if needs_opts:
                oj = _options_to_db(opts_raw)
            elif opts_raw is not None and isinstance(opts_raw, list) and len(opts_raw) > 0:
                oj = json.dumps(opts_raw, ensure_ascii=False)
            else:
                oj = _options_to_db(None)

            prepared.append((qid, label, qtype, oj, sort_order, ck, 1 if is_act else 0))

        print(f"Manifiesto: {manifest_path}")
        print(f"Preguntas en manifiesto: {len(entries)}")
        print(f"IDs en BD (total): {len(existing_ids)}")
        print(f"A actualizar (existen en BD y pasan filtro): {len(prepared)}")
        if skipped_absent:
            print(f"Omitidas (id del manifiesto no existe en BD): {sorted(set(skipped_absent))}")
        print(f"Modo: {'APLICAR' if write_db else 'SIMULACIÓN'}")

        sql = """
            UPDATE survey_questions
            SET label = %s,
                question_type = %s,
                options_json = %s,
                sort_order = %s,
                contract_kind = %s,
                is_active = %s
            WHERE id = %s
        """

        for row in prepared:
            qid, label, qtype, oj, sort_order, ck, ia = row
            vals = (label, qtype, oj, sort_order, ck, ia, qid)
            if not write_db:
                print(f"  → id={qid} | {ck} | {qtype} | sort={sort_order} | active={ia} | {label[:56]}...")
                continue
            cur.execute(sql, vals)

        if write_db:
            conn.commit()
            print(f"Listo: {len(prepared)} fila(s) actualizada(s).")

        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
