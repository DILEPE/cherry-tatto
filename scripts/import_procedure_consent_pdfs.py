#!/usr/bin/env python3
"""
Inserta o actualiza los PDF de consentimiento **solo** en la tabla `procedure_consent_documents`.

Codifica cada PDF a Base64 en memoria y lo persiste en MySQL (no genera archivos .b64 en disco).

Requiere `.env` con DB_* igual que la API y la migración `020_procedure_consent_documents.sql`.

Uso:
    python scripts/import_procedure_consent_pdfs.py --pdf-dir "%USERPROFILE%\\Downloads"
"""
from __future__ import annotations

import argparse
import base64
import os
import sys
from pathlib import Path

try:
    import mysql.connector
except ImportError:
    print("pip install mysql-connector-python python-dotenv", file=sys.stderr)
    raise

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[misc, assignment]

# (etiqueta en survey_option_label / BD, nombre guardado en source_filename, nombres de archivo a buscar en carpeta)
PROCEDURE_PDF_IMPORT: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("Helix", "Helix.pdf", ("Helix.pdf",)),
    ("Lobulos", "Lobulos.pdf", ("Lobulos.pdf",)),
    ("Expansion Lobulos", "Expansion Lobulos.pdf", ("Expansion Lobulos.pdf",)),
    ("Nostril", "Nostril.pdf", ("Nostril.pdf", "Nostry.pdf")),
    ("Tatuaje", "Tatuaje.pdf", ("Tatuaje.pdf",)),
    ("Surface", "Surface.pdf", ("Surface.pdf",)),
    ("Microdermal", "Microdermal.pdf", ("Microdermal.pdf",)),
    ("Septum", "Septum.pdf", ("Septum.pdf",)),
    ("Labio", "Labio.pdf", ("Labio.pdf",)),
    ("Ombligo", "Ombligo.pdf", ("Ombligo.pdf",)),
    ("Pezon", "Pezon.pdf", ("Pezon.pdf",)),
    ("Ceja", "Ceja.pdf", ("Ceja.pdf",)),
    ("Conch", "Conch.pdf", ("Conch.pdf",)),
    ("Industrial", "Industrial.pdf", ("Industrial.pdf",)),
    ("Upper Lobe", "Upper Lobe.pdf", ("Upper Lobe.pdf",)),
    ("Tragus", "Tragus.pdf", ("Tragus.pdf",)),
    ("Lengua", "Lengua.pdf", ("Lengua.pdf",)),
    ("Cristina", "Cristina.pdf", ("Cristina.pdf",)),
    ("Daith", "Daith.pdf", ("Daith.pdf",)),
    ("Rook", "Rook.pdf", ("Rook.pdf",)),
    ("Antihelix", "Antihelix.pdf", ("Antihelix.pdf",)),
    ("Contrahelix", "Contrahelix.pdf", ("Contrahelix.pdf",)),
    ("Flat", "Flat.pdf", ("Flat.pdf",)),
)


def _resolve_pdf_path(pdf_dir: Path, candidates: tuple[str, ...]) -> tuple[Path | None, str | None]:
    for name in candidates:
        p = pdf_dir / name
        if p.is_file():
            return p, name
    return None, None


def main() -> int:
    if load_dotenv:
        load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf-dir", type=Path, required=True)
    ns = ap.parse_args()
    pdf_dir = ns.pdf_dir.expanduser().resolve()
    if not pdf_dir.is_dir():
        print(f"Carpeta inválida: {pdf_dir}", file=sys.stderr)
        return 1

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
        n = 0
        for label, stored_fname, candidates in PROCEDURE_PDF_IMPORT:
            src, used_disk = _resolve_pdf_path(pdf_dir, candidates)
            if src is None:
                print(f"Falta archivo (probado: {', '.join(candidates)}) en {pdf_dir}", file=sys.stderr)
                return 2
            b64 = base64.standard_b64encode(src.read_bytes()).decode("ascii")
            cur.execute(
                """
                REPLACE INTO procedure_consent_documents (survey_option_label, source_filename, pdf_base64)
                VALUES (%s, %s, %s)
                """,
                (label, stored_fname, b64),
            )
            n += 1
            note = f" [{used_disk}]" if used_disk != stored_fname else ""
            print(f"UPSERT {label} ({stored_fname}){note}")
        cur.execute(
            "DELETE FROM procedure_consent_documents WHERE survey_option_label = %s",
            ("Nostry",),
        )
        conn.commit()
        print(f"Listo: {n} filas en procedure_consent_documents.")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
