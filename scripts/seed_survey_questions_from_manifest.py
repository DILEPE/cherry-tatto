#!/usr/bin/env python3
"""
Pobla o actualiza `survey_questions` desde un manifiesto JSON.

**Solo aplica entradas con `"is_active": true`.** Las que tienen `false` se omiten por completo
(no se insertan ni actualizan).

Cada ítem debe llevar **`id` fijo** para poder repetir el script (UPSERT por clave primaria):
inserta la fila o actualiza label/tipo/opciones/orden/ámbito/activo si ya existía.

Requisitos: migraciones de encuestas aplicadas (`011`+ y columna `contract_kind` de `013`).
La pregunta **id 3** coincide con `021_survey_question_3_procedure_options.sql` (procedimientos piercing).

Volcar la tabla actual a JSON (por ejemplo antes de migrar de servidor)::

    python scripts/export_survey_questions_to_manifest.py -o scripts/data/mi_volcado.json

Si en destino **ya hay filas** y solo quieres actualizarlas desde el JSON **sin insertar** nuevas,
usa ``backfill_survey_questions_existing.py --manifest ... --apply``.

Uso (desde la raíz del proyecto)::

    python scripts/seed_survey_questions_from_manifest.py
    python scripts/seed_survey_questions_from_manifest.py --manifest scripts/data/survey_questions_manifest.json
    python scripts/seed_survey_questions_from_manifest.py --apply

Sin `--apply`, solo simulación.
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
    from mysql.connector import Error as MySQLError
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
    raise ValueError(f"options debe ser lista JSON o null, recibido: {type(raw_options)!r}")


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
        help="Ruta al JSON de preguntas.",
    )
    ap.add_argument("--apply", action="store_true", help="Ejecutar UPSERT en MySQL.")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo simulación aunque exista --apply.",
    )
    ns = ap.parse_args()

    manifest_path = ns.manifest.expanduser().resolve()
    if not manifest_path.is_file():
        print(f"No existe el manifiesto: {manifest_path}", file=sys.stderr)
        return 1

    entries = _load_manifest(manifest_path)
    active = [e for e in entries if e.get("is_active") is True]
    skipped = len(entries) - len(active)

    ids_seen: set[int] = set()
    prepared: list[tuple[int, str, str, str | None, int, str, int]] = []

    for e in active:
        qid = e.get("id")
        if qid is None:
            print("Cada pregunta activa debe incluir 'id' entero.", file=sys.stderr)
            return 1
        qid = int(qid)
        if qid in ids_seen:
            print(f"id duplicado en manifiesto: {qid}", file=sys.stderr)
            return 1
        ids_seen.add(qid)

        label = str(e.get("label") or "").strip()
        qtype = str(e.get("question_type") or "").strip()
        sort_order = int(e.get("sort_order") or 0)
        ck = str(e.get("contract_kind") or "tattoo").strip().lower()

        if not label:
            print(f"id={qid}: label obligatorio.", file=sys.stderr)
            return 1
        if qtype not in _QUESTION_TYPES:
            print(f"id={qid}: question_type inválido '{qtype}'.", file=sys.stderr)
            return 1
        if ck not in _CONTRACT_KINDS:
            print(f"id={qid}: contract_kind debe ser tattoo, piercing o both.", file=sys.stderr)
            return 1

        needs_opts = qtype in ("radio", "checkbox", "select")
        opts_raw = e.get("options")
        if needs_opts and (opts_raw is None or (isinstance(opts_raw, list) and len(opts_raw) == 0)):
            print(f"id={qid}: question_type '{qtype}' requiere 'options' no vacío.", file=sys.stderr)
            return 1

        oj = _options_to_db(opts_raw if needs_opts else (opts_raw if opts_raw is not None else None))
        if not needs_opts and opts_raw is not None and isinstance(opts_raw, list) and len(opts_raw) > 0:
            oj = json.dumps(opts_raw, ensure_ascii=False)

        active_int = 1 if e.get("is_active") is True else 0
        prepared.append((qid, label, qtype, oj, sort_order, ck, active_int))

    host = os.getenv("DB_HOST")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    database = os.getenv("DB_NAME", "cherry_tatto")
    if not host or not user or password is None:
        print("Define DB_HOST, DB_USER, DB_PASSWORD (y opcional DB_NAME) en .env", file=sys.stderr)
        return 1

    write_db = bool(ns.apply) and not bool(ns.dry_run)

    print(f"Manifiesto: {manifest_path}")
    print(f"Preguntas en archivo: {len(entries)} | Omitidas (is_active=false): {skipped}")
    print(f"A aplicar (activas): {len(prepared)}")
    print(f"Modo: {'APLICAR' if write_db else 'SIMULACIÓN'}")

    upsert_sql_with_ck = """
        INSERT INTO survey_questions
            (id, label, question_type, options_json, sort_order, contract_kind, is_active)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            label = VALUES(label),
            question_type = VALUES(question_type),
            options_json = VALUES(options_json),
            sort_order = VALUES(sort_order),
            contract_kind = VALUES(contract_kind),
            is_active = VALUES(is_active)
    """

    if not write_db:
        for row in prepared:
            qid, label, qtype, oj, sort_order, ck, ia = row
            opt_note = ""
            if oj:
                try:
                    opt_note = f"opts={len(json.loads(oj))} "
                except json.JSONDecodeError:
                    opt_note = "opts=? "
            print(f"  id={qid} | {ck} | {qtype} | sort={sort_order} | active={ia} | {opt_note}{label[:48]}...")
        print("Usa --apply (sin --dry-run) para escribir en la base.")
        return 0

    conn = mysql.connector.connect(host=host, user=user, password=password, database=database)
    try:
        cur = conn.cursor()
        try:
            has_ck = _has_contract_kind_column(cur)
        except MySQLError as ex:
            print(f"No se pudo comprobar columnas: {ex}", file=sys.stderr)
            return 1

        if not has_ck:
            print(
                "La tabla survey_questions no tiene contract_kind. Aplica la migración 013 antes.",
                file=sys.stderr,
            )
            return 1

        sql = upsert_sql_with_ck
        for row in prepared:
            cur.execute(sql, row)
        conn.commit()
        print(f"Listo: {len(prepared)} pregunta(s) sincronizada(s).")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
