#!/usr/bin/env python3
"""
Genera citas de demostración con contrato firmado y encuesta contestada (para probar reportes).

Requisitos: MySQL accesible con las mismas variables que la API (`.env`), migraciones de
encuestas aplicadas (`011`+), al menos una plantilla de contrato (`contract_templates`) y
preguntas activas en `survey_questions` que quieras ver agregadas en **Reporte**.

Uso (desde la raíz del proyecto):
    python scripts/seed_demo_surveys.py
    python scripts/seed_demo_surveys.py --count 30 --clean

`--clean` borra datos previos generados por este script (detalle de cita y documentos DEMO-SRV-*).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from typing import Any, Optional

try:
    import mysql.connector
    from mysql.connector import Error as MySQLError
except ImportError:
    print("Instala dependencias: pip install mysql-connector-python python-dotenv", file=sys.stderr)
    raise

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[misc, assignment]

DETAIL_MARKER = "[demo_encuestas_reporte]"
DOC_PREFIX = "DEMO-SRV-"
EMAIL_DOMAIN = "demo-encuesta.local"


def parse_options_json(raw: Any) -> Optional[list[str]]:
    if raw is None:
        return None
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return None
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [str(x).strip() for x in data if str(x).strip()]
        except json.JSONDecodeError:
            return None
    return None


def appointment_contract_kind(service_type: str) -> str:
    s = (service_type or "").strip().lower()
    if "tatu" in s or s == "tattoo":
        return "tattoo"
    return "piercing"


def question_applies(row: dict[str, Any], appt_kind: str) -> bool:
    ck = str(row.get("contract_kind") or "tattoo").strip().lower()
    if ck not in ("tattoo", "piercing", "both"):
        ck = "tattoo"
    if ck == "both":
        return True
    return ck == appt_kind


def clean_demo_data(cursor: Any) -> None:
    # Evitar '%' en el SQL: mysql.connector lo mezcla con placeholders y lanza
    # "Not all parameters were used". LOCATE / CHAR(37) en MySQL equivalen a contiene / comodín LIKE.
    mid = DETAIL_MARKER
    cursor.execute(
        """
        DELETE sa FROM survey_answers sa
        INNER JOIN surveys s ON s.id = sa.survey_id
        INNER JOIN appointments a ON a.id = s.appointment_id
        WHERE LOCATE(%s, a.detail) > 0
        """,
        (mid,),
    )
    cursor.execute(
        """
        DELETE s FROM surveys s
        INNER JOIN appointments a ON a.id = s.appointment_id
        WHERE LOCATE(%s, a.detail) > 0
        """,
        (mid,),
    )
    cursor.execute(
        """
        DELETE c FROM contracts c
        INNER JOIN appointments a ON a.id = c.appointment_id
        WHERE LOCATE(%s, a.detail) > 0
        """,
        (mid,),
    )
    cursor.execute(
        "DELETE FROM appointments WHERE LOCATE(%s, detail) > 0",
        (mid,),
    )
    cursor.execute(
        "DELETE FROM customers WHERE document_number LIKE CONCAT(%s, CHAR(37))",
        (DOC_PREFIX,),
    )


def pick_template_id(cursor: Any) -> Optional[int]:
    cursor.execute(
        """
        SELECT id FROM contract_templates
        WHERE is_active = 1
        ORDER BY id DESC
        LIMIT 1
        """
    )
    row = cursor.fetchone()
    if row:
        return int(row[0])
    cursor.execute("SELECT id FROM contract_templates ORDER BY id DESC LIMIT 1")
    row2 = cursor.fetchone()
    return int(row2[0]) if row2 else None


def load_active_questions(cursor: Any) -> list[dict[str, Any]]:
    try:
        cursor.execute(
            """
            SELECT id, label, question_type, options_json, sort_order, contract_kind, is_active
            FROM survey_questions
            WHERE is_active = 1
            ORDER BY sort_order ASC, id ASC
            """
        )
    except MySQLError:
        cursor.execute(
            """
            SELECT id, label, question_type, options_json, sort_order, is_active
            FROM survey_questions
            WHERE is_active = 1
            ORDER BY sort_order ASC, id ASC
            """
        )
    rows = cursor.fetchall()
    cols = [d[0] for d in (cursor.description or ())]
    return [dict(zip(cols, row)) for row in rows]


def build_answer_cells(
    q: dict[str, Any],
    seed_idx: int,
) -> tuple[Optional[int], Optional[bool], Optional[str], Optional[float]]:
    """Devuelve (answer_rating, answer_bool, answer_text, answer_number)."""
    qt = str(q.get("question_type") or "text_short")
    opts = parse_options_json(q.get("options_json"))

    if qt == "rating_1_5":
        return (seed_idx % 5) + 1, None, None, None
    if qt == "yes_no":
        return None, (seed_idx % 2 == 0), None, None
    if qt == "number":
        return None, None, None, round(2.0 + (seed_idx % 12) * 0.5, 4)
    if qt in ("text", "textarea", "text_short"):
        return None, None, f"Comentario demo #{seed_idx + 1} — variación para reporte.", None
    if qt in ("radio", "select"):
        if not opts:
            return None, None, None, None
        return None, None, opts[seed_idx % len(opts)], None
    if qt == "checkbox":
        if not opts:
            return None, None, None, None
        if len(opts) >= 2:
            picked = [opts[0], opts[seed_idx % len(opts)]]
        else:
            picked = [opts[0]]
        return None, None, json.dumps(picked, ensure_ascii=False), None
    return None, None, f"Otro tipo {qt} demo {seed_idx}", None


def aggregate_survey_row(
    answers: list[tuple[Any, Any, Any, Any]],
) -> tuple[int, str]:
    """rating y comments consolidados (fila surveys)."""
    ratings = [a[0] for a in answers if a[0] is not None]
    texts: list[str] = []
    for a in answers:
        if a[2] and str(a[2]).strip():
            texts.append(str(a[2]).strip())
    rating_avg = int(round(sum(ratings) / len(ratings))) if ratings else 3
    comments = " | ".join(texts[:8]) if texts else "Encuesta demo (reporte)"
    return rating_avg, comments[:4999]


def insert_customer(cursor: Any, idx: int, batch: int) -> int:
    doc = f"{DOC_PREFIX}{batch}-{idx:04d}"
    email = f"demo_{batch}_{idx:04d}@{EMAIL_DOMAIN}"
    phone = f"300{idx % 1000000:06d}"
    sql = """
        INSERT INTO customers (
            first_name, last_name, birth_date, document_type, document_number,
            document_issue_date,
            email, phone_number, address, nationality, profession,
            social_media, emergency_contact_name, emergency_contact_phone,
            is_minor, guardian_name, guardian_document_type, guardian_document_number,
            guardian_document_issue_date
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
    """
    cursor.execute(
        sql,
        (
            "Demo",
            f"Cliente{idx}",
            date(1992, 1, (idx % 28) + 1),
            "CC",
            doc,
            None,
            email,
            phone,
            "Calle demo",
            "CO",
            None,
            None,
            None,
            None,
            False,
            None,
            None,
            None,
            None,
        ),
    )
    return int(cursor.lastrowid or 0)


def insert_appointment_full(
    cursor: Any,
    customer_id: int,
    name: str,
    phone: str,
    service_type: str,
    appt_dt: datetime,
    detail: str,
) -> int:
    try:
        cursor.execute(
            """
            INSERT INTO appointments (
                customer_id, customer_name, phone, service_type, detail,
                appointment_date, deposit, total_amount, pending_balance,
                customer_credit, is_priority, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                customer_id,
                name,
                phone,
                service_type,
                detail,
                appt_dt.strftime("%Y-%m-%d %H:%M:%S"),
                100_000.0,
                500_000.0,
                400_000.0,
                0.0,
                0,
                "Finalizada",
            ),
        )
    except MySQLError as e:
        err = str(e)
        if "Unknown column" not in err:
            raise
        cursor.execute(
            """
            INSERT INTO appointments (
                customer_id, customer_name, phone, service_type, detail,
                appointment_date, deposit, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                customer_id,
                name,
                phone,
                service_type,
                detail,
                appt_dt.strftime("%Y-%m-%d %H:%M:%S"),
                100_000.0,
                "Finalizada",
            ),
        )
    return int(cursor.lastrowid or 0)


def insert_contract(cursor: Any, appointment_id: int, template_id: Optional[int]) -> None:
    health = json.dumps({"source": "seed_demo_surveys", "template_id": template_id})
    stub = "demofirma"
    cursor.execute(
        """
        INSERT INTO contracts (
            appointment_id, template_id, is_minor, health_data,
            client_signature, tutor_signature, artist_signature,
            tutor_document_front, tutor_document_back, contract_text
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            appointment_id,
            template_id,
            0,
            health,
            stub,
            None,
            stub,
            None,
            None,
            "<p>Contrato demo generado por scripts/seed_demo_surveys.py</p>",
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Sembrar citas con contrato y encuesta para reportes.")
    parser.add_argument("--count", type=int, default=30, help="Número de citas a crear (default 30)")
    parser.add_argument("--clean", action="store_true", help="Borra datos demo previos de este script")
    args = parser.parse_args()

    if load_dotenv:
        load_dotenv()

    host = os.getenv("DB_HOST", "localhost")
    user = os.getenv("DB_USER", "root")
    password = os.getenv("DB_PASSWORD", "")
    database = os.getenv("DB_NAME", "cherry_tatto")

    try:
        conn = mysql.connector.connect(host=host, user=user, password=password, database=database)
    except MySQLError as e:
        print(f"No se pudo conectar a MySQL ({database}): {e}", file=sys.stderr)
        return 1

    batch = int(time.time())
    cursor = conn.cursor(buffered=True)
    try:
        if args.clean:
            clean_demo_data(cursor)
            conn.commit()
            print("Limpieza de datos demo previa completada.")

        all_questions = load_active_questions(cursor)
        if not all_questions:
            print(
                "No hay preguntas activas en survey_questions. "
                "Crea preguntas en el panel (Gestión encuesta) y vuelve a ejecutar.",
                file=sys.stderr,
            )
            return 2

        tpl_id = pick_template_id(cursor)
        if tpl_id is None:
            print("No hay plantillas en contract_templates. Crea al menos una plantilla.", file=sys.stderr)
            return 3

        base_date = date.today() - timedelta(days=60)
        created = 0
        for i in range(args.count):
            service_type = "Tatuaje" if i % 2 == 0 else "Piercing"
            appt_kind = appointment_contract_kind(service_type)
            applicable = [q for q in all_questions if question_applies(q, appt_kind)]
            if not applicable:
                print(
                    f"Aviso: cita {i} ({service_type}) sin preguntas aplicables "
                    f"(contract_kind). Revisa survey_questions.",
                    file=sys.stderr,
                )

            cid = insert_customer(cursor, i, batch)
            detail = f"{DETAIL_MARKER} batch={batch} n={i}"
            name = f"Demo Cliente{i}"
            phone = f"301{i % 1000000:06d}"
            appt_dt = datetime.combine(base_date, datetime.min.time()) + timedelta(days=i % 45, hours=10 + (i % 6))

            aid = insert_appointment_full(cursor, cid, name, phone, service_type, appt_dt, detail)
            insert_contract(cursor, aid, tpl_id)

            cells: list[tuple[Any, Any, Any, Any]] = []
            q_ids: list[int] = []
            for q in applicable:
                ar, ab, atxt, anum = build_answer_cells(q, i)
                if ar is None and ab is None and (atxt is None or atxt == "") and anum is None:
                    continue
                cells.append((ar, ab, atxt, anum))
                q_ids.append(int(q["id"]))

            would_rec = (i % 3) != 1
            rating, comments = aggregate_survey_row(cells)

            cursor.execute(
                """
                INSERT INTO surveys (appointment_id, rating, comments, would_recommend)
                VALUES (%s, %s, %s, %s)
                """,
                (aid, rating, comments, would_rec),
            )
            sid = int(cursor.lastrowid or 0)
            for qid, cell in zip(q_ids, cells):
                ar, ab, atxt, anum = cell
                cursor.execute(
                    """
                    INSERT INTO survey_answers (survey_id, question_id, answer_rating, answer_bool, answer_text, answer_number)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (sid, qid, ar, ab, atxt, anum),
                )
            created += 1

        conn.commit()
        print(f"Listo: {created} citas con contrato y encuesta (batch={batch}).")
        print("Revisa en Streamlit: pestaña Reporte -> bloque Encuestas.")
    except MySQLError as e:
        conn.rollback()
        print(f"Error SQL: {e}", file=sys.stderr)
        return 4
    finally:
        cursor.close()
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
