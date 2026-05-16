#!/usr/bin/env python3
"""
Regenera `contracts.contract_text` a partir del HTML de la plantilla **activa** vinculada
(`contract_templates.is_active = 1` y mismo `template_id`).

Replica la sustitución de placeholders y el bloque de tutor para menores, alineado con
`streamlit_app/contract_signing.py` (firma guardada).

Requisitos: `.env` con DB_* como la API; ejecutar desde la raíz del repo:

    python scripts/backfill_contract_text_active_templates.py --dry-run
    python scripts/backfill_contract_text_active_templates.py --apply
    python scripts/backfill_contract_text_active_templates.py --apply --force-all

Sin flags solo lista candidatos (modo simulación). Escritura solo con `--apply`
(sin `--dry-run`; si pasas ambos, prevalece la simulación).
"""
from __future__ import annotations

import argparse
import html
import os
import sys
from pathlib import Path
from typing import Any, Mapping

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    import mysql.connector
except ImportError:
    print("pip install mysql-connector-python python-dotenv", file=sys.stderr)
    raise

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[misc, assignment]

from app.domain.contract_kinds import appointment_to_contract_kind


def _customer_row_to_dict(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "first_name": row.get("first_name") or "",
        "last_name": row.get("last_name") or "",
        "document_type": row.get("document_type") or "",
        "document_number": row.get("document_number") or "",
        "document_issue_date": row.get("document_issue_date"),
        "guardian_name": row.get("guardian_name") or "",
        "guardian_document_type": row.get("guardian_document_type") or "",
        "guardian_document_number": row.get("guardian_document_number") or "",
        "guardian_document_issue_date": row.get("guardian_document_issue_date"),
        "is_minor": bool(row.get("is_minor")),
    }


def render_contract_text(template_content: str, customer: dict[str, Any]) -> str:
    is_minor = bool(customer.get("is_minor"))
    di = customer.get("document_issue_date")
    gdi = customer.get("guardian_document_issue_date")
    replacements = {
        "{{nombres}}": f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip(),
        "{{identificacion}}": str(customer.get("document_type") or ""),
        "{{numero_documento}}": str(customer.get("document_number") or ""),
        "{{fecha_expedicion}}": "" if di is None else str(di),
        "{{nombre_tutor}}": str(customer.get("guardian_name") or "") if is_minor else "",
        "{{identificacion_tutor}}": str(customer.get("guardian_document_type") or "") if is_minor else "",
        "{{numero_documento_tutor}}": str(customer.get("guardian_document_number") or "") if is_minor else "",
        "{{fecha_expedicion_tutor}}": ("" if gdi is None else str(gdi)) if is_minor else "",
    }
    out = template_content
    for k, v in replacements.items():
        out = out.replace(k, v)
    return out


def _procedure_noun_es(appointment: dict[str, Any]) -> str:
    return "tatuaje" if appointment_to_contract_kind(appointment) == "tattoo" else "piercing"


def minor_guardian_declaration_panel_html(
    customer: dict[str, Any],
    appointment: dict[str, Any],
    *,
    tutor_name: str,
) -> str:
    proc = html.escape(_procedure_noun_es(appointment))
    nombre_cliente = html.escape(
        f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip()
    )
    nt = tutor_name.strip()
    nombre_tutor = html.escape(nt) if nt else "________________"
    auth = (
        f'<p style="margin:0;">'
        f"Autorizo en calidad de padre o madre, <strong>{nombre_tutor}</strong>, a mi hijo/a "
        f"<strong>{nombre_cliente}</strong> a realizarse el <strong>{proc}</strong> en el lugar del cuerpo que se ha "
        f"especificado en este documento bajo mi única responsabilidad.</p>"
    )
    fn = f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip()
    dt = str(customer.get("document_type") or "")
    dn = str(customer.get("document_number") or "").strip()
    client_line = (
        f'<p style="margin:0 0 0.85rem 0;font-size:0.95rem;line-height:1.55;">'
        f"<strong>Cliente:</strong> "
        f"{html.escape(fn)} · {html.escape(dt)} {html.escape(dn)}</p>"
    )
    return f'<div class="ctsig-declaration-alert">{client_line}{auth}</div>'


def build_contract_body(
    template_content: str,
    customer: dict[str, Any],
    appointment: dict[str, Any],
    *,
    contract_is_minor: bool,
) -> str:
    base = render_contract_text(template_content, customer)
    if not contract_is_minor:
        return base
    gn = str(customer.get("guardian_name") or "").strip()
    return base + minor_guardian_declaration_panel_html(customer, appointment, tutor_name=gn)


def main() -> int:
    if load_dotenv:
        load_dotenv()

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Lista contratos candidatos sin escribir en BD (por defecto si no pasas --apply).",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Ejecuta UPDATE en contracts.contract_text.",
    )
    ap.add_argument(
        "--force-all",
        action="store_true",
        help="Incluye contratos que ya tienen contract_text (sin esto, solo vacíos/NULL).",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Máximo de filas a procesar (0 = sin límite).",
    )
    ns = ap.parse_args()

    write_db = bool(ns.apply) and not bool(ns.dry_run)

    host = os.getenv("DB_HOST")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    database = os.getenv("DB_NAME", "cherry_tatto")
    if not host or not user or password is None:
        print("Define DB_HOST, DB_USER, DB_PASSWORD (y opcional DB_NAME) en .env", file=sys.stderr)
        return 1

    empty_clause = ""
    if not ns.force_all:
        empty_clause = " AND (c.contract_text IS NULL OR TRIM(c.contract_text) = '')"

    limit_clause = f" LIMIT {int(ns.limit)}" if ns.limit and ns.limit > 0 else ""

    sql_select = f"""
        SELECT
            c.id AS contract_id,
            c.appointment_id,
            c.template_id,
            c.is_minor AS contract_is_minor,
            tpl.content AS template_content,
            a.customer_id,
            a.service_type,
            cust.first_name,
            cust.last_name,
            cust.document_type,
            cust.document_number,
            cust.document_issue_date,
            cust.guardian_name,
            cust.guardian_document_type,
            cust.guardian_document_number,
            cust.guardian_document_issue_date,
            c.contract_text AS old_contract_text
        FROM contracts c
        INNER JOIN contract_templates tpl
            ON tpl.id = c.template_id AND tpl.is_active = 1
        INNER JOIN appointments a ON a.id = c.appointment_id
        LEFT JOIN customers cust ON cust.id = a.customer_id
        WHERE c.template_id IS NOT NULL
        {empty_clause}
        ORDER BY c.id ASC
        {limit_clause}
    """

    conn = mysql.connector.connect(host=host, user=user, password=password, database=database)
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql_select)
        rows = cur.fetchall()
        mode = "APLICAR" if write_db else "SIMULACIÓN"
        print(f"[{mode}] Contratos candidatos (plantilla activa): {len(rows)}")
        updated = 0
        skipped = 0

        for row in rows:
            cid = int(row["contract_id"])
            tpl_html = str(row.get("template_content") or "")
            if not tpl_html.strip():
                print(f"  Omitido id={cid}: plantilla sin contenido.")
                skipped += 1
                continue

            cust_raw = {k: row.get(k) for k in (
                "first_name", "last_name", "document_type", "document_number",
                "document_issue_date", "is_minor", "guardian_name",
                "guardian_document_type", "guardian_document_number",
                "guardian_document_issue_date",
            )}
            customer = _customer_row_to_dict(cust_raw)
            contract_is_minor = bool(row.get("contract_is_minor"))
            # Misma semántica que al firmar: placeholders de tutor según el menor registrado en el contrato.
            customer["is_minor"] = contract_is_minor
            appointment = {"service_type": row.get("service_type") or ""}

            body = build_contract_body(
                tpl_html,
                customer,
                appointment,
                contract_is_minor=contract_is_minor,
            )

            if not write_db:
                preview = "sí" if (row.get("old_contract_text") or "").strip() else "vacío"
                print(f"  id={cid} appointment={row['appointment_id']} template={row['template_id']} texto_actual={preview}")
                continue

            cur_u = conn.cursor()
            cur_u.execute(
                "UPDATE contracts SET contract_text = %s WHERE id = %s",
                (body, cid),
            )
            updated += cur_u.rowcount or 0

        if write_db:
            conn.commit()
            print(f"Filas actualizadas: {updated}. Omitidos: {skipped}.")
        else:
            print("Usa --apply (sin --dry-run) para escribir cambios (y revisa --force-all si quieres pisar textos existentes).")

        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
