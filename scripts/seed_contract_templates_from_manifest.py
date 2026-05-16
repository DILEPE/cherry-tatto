#!/usr/bin/env python3
"""
Pobla `contract_templates` desde un manifiesto JSON + archivos HTML.

**Solo procesa entradas con `"is_active": true`.** Las que están en `false` se omiten por completo
(no se lee el archivo ni se escribe fila), para no mezclar borradores o versiones viejas.

Tras cada alta activa, desactiva el resto de plantillas del mismo `contract_kind`
(misma regla que `Repositories.create_template`).

Requisitos: `.env` con DB_*; ejecutar desde la raíz del proyecto::

    python scripts/seed_contract_templates_from_manifest.py
    python scripts/seed_contract_templates_from_manifest.py --manifest scripts/data/contract_templates_manifest.json
    python scripts/seed_contract_templates_from_manifest.py --apply

Sin `--apply`, solo muestra qué haría (simulación). Con `--apply`, si ya existe la misma
tupla (contract_kind, name, version), solo actualiza `content` y deja esa fila como activa.
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


def _load_manifest(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get("templates")
    if not isinstance(raw, list):
        raise ValueError("El manifiesto debe tener una clave 'templates' (lista).")
    return [x for x in raw if isinstance(x, dict)]


def main() -> int:
    if load_dotenv:
        load_dotenv()

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--manifest",
        type=Path,
        default=_REPO_ROOT / "scripts/data/contract_templates_manifest.json",
        help="Ruta al JSON de plantillas.",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Ejecutar INSERT en MySQL.",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Fuerza solo simulación aunque exista --apply.",
    )
    ns = ap.parse_args()

    manifest_path = ns.manifest.expanduser().resolve()
    if not manifest_path.is_file():
        print(f"No existe el manifiesto: {manifest_path}", file=sys.stderr)
        return 1

    entries = _load_manifest(manifest_path)
    active = [e for e in entries if e.get("is_active") is True]
    skipped_inactive = len(entries) - len(active)

    by_kind: dict[str, list[dict[str, Any]]] = {}
    for e in active:
        kind = str(e.get("contract_kind") or "").strip().lower()
        if kind not in ("tattoo", "piercing"):
            print(f"contract_kind inválido en entrada {e!r}: use tattoo o piercing", file=sys.stderr)
            return 1
        by_kind.setdefault(kind, []).append(e)
    for kind, lst in by_kind.items():
        if len(lst) > 1:
            print(
                f"Hay más de una plantilla activa para '{kind}' en el manifiesto "
                f"({len(lst)}). Deja solo una con is_active true por tipo.",
                file=sys.stderr,
            )
            return 1

    host = os.getenv("DB_HOST")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    database = os.getenv("DB_NAME", "cherry_tatto")
    if not host or not user or password is None:
        print("Define DB_HOST, DB_USER, DB_PASSWORD (y opcional DB_NAME) en .env", file=sys.stderr)
        return 1

    write_db = bool(ns.apply) and not bool(ns.dry_run)

    print(f"Manifiesto: {manifest_path}")
    print(f"Entradas totales: {len(entries)} | Omitidas (is_active=false): {skipped_inactive}")
    print(f"A insertar (activas): {len(active)}")
    print(f"Modo: {'APLICAR' if write_db else 'SIMULACIÓN'}")

    prepared: list[tuple[str, str, str, str, str]] = []
    for e in active:
        rel = str(e.get("file") or "").strip()
        name = str(e.get("name") or "").strip()
        version = str(e.get("version") or "").strip()
        kind = str(e.get("contract_kind") or "").strip().lower()
        if not rel or not name or not version:
            print(f"Entrada incompleta (file, name, version obligatorios): {e!r}", file=sys.stderr)
            return 1
        html_path = (_REPO_ROOT / rel).resolve()
        if not html_path.is_file():
            print(f"No existe el HTML: {html_path}", file=sys.stderr)
            return 1
        content = html_path.read_text(encoding="utf-8")
        prepared.append((name, kind, version, content, rel))

    if not write_db:
        for name, kind, version, _content, rel in prepared:
            print(f"  + {kind} | {name} | v{version} ← {rel}")
        print("Usa --apply (sin --dry-run) para cargar en la base.")
        return 0

    conn = mysql.connector.connect(host=host, user=user, password=password, database=database)
    try:
        cur = conn.cursor()
        upserted = 0
        for name, kind, version, content, rel in prepared:
            cur.execute(
                """
                SELECT id FROM contract_templates
                WHERE contract_kind = %s AND name = %s AND version = %s
                LIMIT 1
                """,
                (kind, name, version),
            )
            row = cur.fetchone()
            if row:
                tid = int(row[0])
                cur.execute(
                    """
                    UPDATE contract_templates
                    SET content = %s, is_active = 1
                    WHERE id = %s
                    """,
                    (content, tid),
                )
                action = "actualizada"
            else:
                cur.execute(
                    """
                    INSERT INTO contract_templates (name, contract_kind, version, content, is_active)
                    VALUES (%s, %s, %s, %s, 1)
                    """,
                    (name, kind, version, content),
                )
                tid = int(cur.lastrowid or 0)
                action = "insertada"

            if tid:
                cur.execute(
                    """
                    UPDATE contract_templates
                    SET is_active = 0
                    WHERE contract_kind = %s AND id != %s AND is_active = 1
                    """,
                    (kind, tid),
                )
            upserted += 1
            print(f"  {action} id={tid} {kind} | {name} | v{version} ← {rel}")
        conn.commit()
        print(f"Listo: {upserted} plantilla(s) activa(s) sincronizada(s).")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
