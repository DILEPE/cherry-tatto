import json
from typing import Any, Optional
from app.domain.models import (
    AppointmentCreate,
    ContractSign,
    ContractTemplate,
    Survey,
    SurveyQuestion,
)
from app.domain.service_types import resolve_service_type

class AppointmentRepository:
    """
    Capa de persistencia: Gestiona SQL para citas, contratos y plantillas.
    """
    
    def __init__(self, db_manager):
        self.db = db_manager

    def _get_cursor(self, conn, dictionary=False):
        """Helper para obtener un cursor de forma segura."""
        if conn is None:
            raise ConnectionError("No se pudo establecer conexión con MySQL.")
        return conn.cursor(dictionary=dictionary)

    # --- Métodos de Citas ---

    def get_all(self, assigned_panel_user_id: Optional[int] = None) -> list[dict[str, object]]:
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn, dictionary=True)
            if assigned_panel_user_id is None:
                cursor.execute(
                    """
                    SELECT a.*,
                        EXISTS (SELECT 1 FROM contracts c WHERE c.appointment_id = a.id)
                            AS has_signed_contract,
                        pu.username AS assigned_username,
                        pu.first_name AS assigned_first_name,
                        pu.last_name AS assigned_last_name,
                        pu.role AS assigned_role
                    FROM appointments a
                    LEFT JOIN panel_users pu ON pu.id = a.assigned_panel_user_id
                    ORDER BY a.created_at DESC
                    """
                )
            else:
                cursor.execute(
                    """
                    SELECT a.*,
                        EXISTS (SELECT 1 FROM contracts c WHERE c.appointment_id = a.id)
                            AS has_signed_contract,
                        pu.username AS assigned_username,
                        pu.first_name AS assigned_first_name,
                        pu.last_name AS assigned_last_name,
                        pu.role AS assigned_role
                    FROM appointments a
                    LEFT JOIN panel_users pu ON pu.id = a.assigned_panel_user_id
                    WHERE a.assigned_panel_user_id = %s
                    ORDER BY a.created_at DESC
                    """,
                    (assigned_panel_user_id,),
                )
            rows = cursor.fetchall()
            for row in rows:
                raw = row.get("has_signed_contract")
                row["has_signed_contract"] = bool(raw) if raw is not None else False
            return rows
        except Exception as e:
            err = str(e)
            if (
                "Unknown column 'a.assigned_panel_user_id'" in err
                or "Unknown column 'assigned_panel_user_id'" in err
            ):
                return self._get_all_legacy_no_assignee()
            raise
        finally:
            if conn:
                conn.close()

    def _get_all_legacy_no_assignee(self) -> list[dict[str, object]]:
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn, dictionary=True)
            cursor.execute(
                """
                SELECT a.*,
                    EXISTS (SELECT 1 FROM contracts c WHERE c.appointment_id = a.id)
                        AS has_signed_contract
                FROM appointments a
                ORDER BY a.created_at DESC
                """
            )
            rows = cursor.fetchall()
            for row in rows:
                raw = row.get("has_signed_contract")
                row["has_signed_contract"] = bool(raw) if raw is not None else False
            return rows
        finally:
            if conn:
                conn.close()

    def create(
        self,
        data: AppointmentCreate,
        customer_id: Optional[int] = None,
        conn=None,
    ) -> int:
        own = conn is None
        if own:
            conn = self.db.get_connection()
        if conn is None:
            raise ConnectionError("No se pudo establecer conexión con MySQL.")
        try:
            cursor = self._get_cursor(conn)
            service_type = resolve_service_type(data.service)
            aid = getattr(data, "assigned_panel_user_id", None)
            assignee_val = int(aid) if aid is not None else None

            def _insert_financial_no_assignee() -> None:
                q = """INSERT INTO appointments
                       (customer_id, customer_name, phone, service_type, detail, appointment_date, deposit, total_amount, pending_balance, customer_credit, is_priority, status)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                cursor.execute(
                    q,
                    (
                        customer_id,
                        data.name,
                        data.phone,
                        service_type,
                        data.detail or "",
                        data.date,
                        data.deposit or 0,
                        data.total_amount or 0,
                        data.pending_balance or 0,
                        0,
                        1 if getattr(data, "is_priority", False) else 0,
                        "Agendada",
                    ),
                )

            def _insert_legacy_minimal() -> None:
                q = """INSERT INTO appointments
                      (customer_id, customer_name, phone, service_type, detail, appointment_date, deposit, status)
                      VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""
                cursor.execute(
                    q,
                    (
                        customer_id,
                        data.name,
                        data.phone,
                        service_type,
                        data.detail or "",
                        data.date,
                        data.deposit or 0,
                        "Agendada",
                    ),
                )

            try:
                q_full = """INSERT INTO appointments
                           (customer_id, assigned_panel_user_id, customer_name, phone, service_type, detail, appointment_date, deposit, total_amount, pending_balance, customer_credit, is_priority, status)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                cursor.execute(
                    q_full,
                    (
                        customer_id,
                        assignee_val,
                        data.name,
                        data.phone,
                        service_type,
                        data.detail or "",
                        data.date,
                        data.deposit or 0,
                        data.total_amount or 0,
                        data.pending_balance or 0,
                        0,
                        1 if getattr(data, "is_priority", False) else 0,
                        "Agendada",
                    ),
                )
            except Exception as e:
                err = str(e)
                if "Unknown column 'assigned_panel_user_id'" in err:
                    try:
                        _insert_financial_no_assignee()
                    except Exception as e2:
                        if "Unknown column 'total_amount'" not in str(e2):
                            raise
                        _insert_legacy_minimal()
                elif "Unknown column 'total_amount'" not in err:
                    raise
                else:
                    _insert_legacy_minimal()
            new_id = cursor.lastrowid
            if own:
                conn.commit()
            return int(new_id)
        finally:
            if own and conn:
                conn.close()

    def get_by_id(self, appointment_id: int) -> Optional[Any]:
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn, dictionary=True)
            cursor.execute("SELECT * FROM appointments WHERE id = %s", (appointment_id,))
            res = cursor.fetchone()
            if res:
                # Retornamos un objeto genérico o mapeado para el servicio
                from types import SimpleNamespace
                return SimpleNamespace(
                    id=res['id'],
                    name=res['customer_name'],
                    phone=res['phone'],
                    service=res['service_type'],
                    date=str(res['appointment_date']),
                    status=res.get('status'),
                    deposit=float(res.get('deposit') or 0),
                    total_amount=float(res.get('total_amount') or 0),
                    pending_balance=float(res.get('pending_balance') or 0),
                )
            return None
        finally:
            if conn: conn.close()

    # --- Métodos de Contratos ---

    def create_contract(self, data: ContractSign) -> int:
        """Guarda la firma del contrato vinculándola a la cita y a la versión de la plantilla."""
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn)
            health_json = json.dumps(data.health_data)
            
            query = """
                INSERT INTO contracts 
                (
                    appointment_id,
                    template_id,
                    is_minor,
                    health_data,
                    client_signature,
                    tutor_signature,
                    artist_signature,
                    tutor_document_front,
                    tutor_document_back,
                    contract_text
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            values = (
                data.appointment_id,
                data.template_id,
                data.is_minor,
                health_json,
                data.signature,
                data.tutor_signature,
                data.artist_signature,
                data.tutor_document_front,
                data.tutor_document_back,
                data.contract_text,
            )
            cursor.execute(query, values)
            contract_id = cursor.lastrowid
            conn.commit()
            return contract_id
        finally:
            if conn: conn.close()

    def has_contract_for_appointment(self, appointment_id: int) -> bool:
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute(
                "SELECT 1 FROM contracts WHERE appointment_id = %s LIMIT 1",
                (appointment_id,),
            )
            return cursor.fetchone() is not None
        finally:
            if conn: conn.close()

    def get_contracts_by_customer(self, customer_id: int) -> list[dict[str, object]]:
        """Lista contratos firmados vinculados a un cliente."""
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn, dictionary=True)
            cursor.execute(
                """
                SELECT
                    c.id,
                    c.appointment_id,
                    c.template_id,
                    c.is_minor,
                    a.customer_name,
                    a.service_type,
                    a.appointment_date
                FROM contracts c
                INNER JOIN appointments a ON a.id = c.appointment_id
                WHERE a.customer_id = %s
                ORDER BY c.id DESC
                """,
                (customer_id,),
            )
            return cursor.fetchall()
        finally:
            if conn:
                conn.close()

    def get_contract_by_id(self, contract_id: int) -> Optional[dict[str, object]]:
        """Detalle completo de un contrato firmado."""
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn, dictionary=True)
            cursor.execute(
                """
                SELECT c.*, a.customer_id, a.customer_name, a.appointment_date, a.service_type
                FROM contracts c
                LEFT JOIN appointments a ON a.id = c.appointment_id
                WHERE c.id = %s
                LIMIT 1
                """,
                (contract_id,),
            )
            return cursor.fetchone()
        finally:
            if conn:
                conn.close()

    def update_status(self, appointment_id: int, status: str):
        """Actualiza el estado de la cita."""
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute("UPDATE appointments SET status = %s WHERE id = %s", (status, appointment_id))
            conn.commit()
        finally:
            if conn: conn.close()

    def update_financials(self, appointment_id: int, total_amount: float, deposit: float, pending_balance: float) -> None:
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute(
                """
                UPDATE appointments
                SET total_amount = %s,
                    deposit = %s,
                    pending_balance = %s
                WHERE id = %s
                """,
                (total_amount, deposit, pending_balance, appointment_id),
            )
            conn.commit()
        finally:
            if conn:
                conn.close()

    def list_payments_by_appointment(self, appointment_id: int) -> list[dict[str, object]]:
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn, dictionary=True)
            cursor.execute(
                """
                SELECT id, appointment_id, amount, note, created_at
                FROM appointment_payments
                WHERE appointment_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (appointment_id,),
            )
            return cursor.fetchall()
        finally:
            if conn:
                conn.close()

    def create_payment(self, appointment_id: int, amount: float, note: Optional[str] = None) -> None:
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute(
                """
                INSERT INTO appointment_payments (appointment_id, amount, note)
                VALUES (%s, %s, %s)
                """,
                (appointment_id, amount, note),
            )
            cursor.execute(
                """
                UPDATE appointments
                SET deposit = COALESCE(deposit, 0) + %s,
                    pending_balance = GREATEST(COALESCE(total_amount, 0) - (COALESCE(deposit, 0) + %s), 0)
                WHERE id = %s
                """,
                (amount, amount, appointment_id),
            )
            conn.commit()
        finally:
            if conn:
                conn.close()

    def cancel_appointment(self, appointment_id: int, on_cancel_abono: str) -> None:
        """
        on_cancel_abono:
        - credito_cliente: traslada el deposit a customer_credit y pone deposit en 0
          para no duplicar en resúmenes (abono deja de figurar como cobrado sobre la cita).
        - devolucion: abono tratado como devuelto; sin crédito y sin deposit en esta cita.
        """
        if on_cancel_abono not in {"credito_cliente", "devolucion"}:
            raise ValueError("on_cancel_abono inválido")
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn)
            if on_cancel_abono == "credito_cliente":
                cursor.execute(
                    """
                    UPDATE appointments
                    SET status = 'Cancelada',
                        pending_balance = 0,
                        customer_credit = COALESCE(deposit, 0),
                        deposit = 0
                    WHERE id = %s
                    """,
                    (appointment_id,),
                )
            else:
                cursor.execute(
                    """
                    UPDATE appointments
                    SET status = 'Cancelada',
                        pending_balance = 0,
                        customer_credit = 0,
                        deposit = 0
                    WHERE id = %s
                    """,
                    (appointment_id,),
                )
            conn.commit()
        finally:
            if conn:
                conn.close()

    def reprogram_appointment(self, appointment_id: int, new_date: str, detail: Optional[str] = None) -> None:
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute(
                """
                UPDATE appointments
                SET appointment_date = %s,
                    detail = %s,
                    status = %s
                WHERE id = %s
                """,
                (new_date, detail or "", "Reprogramada", appointment_id),
            )
            conn.commit()
        finally:
            if conn:
                conn.close()

    # --- Encuestas ---

    def create_survey(self, data: Survey) -> int:
        """Persiste la encuesta y, si aplica, las respuestas por pregunta (survey_answers)."""
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute(
                """
                INSERT INTO surveys (appointment_id, rating, comments, would_recommend)
                VALUES (%s, %s, %s, %s)
                """,
                (data.appointment_id, data.rating, data.comments, data.would_recommend),
            )
            new_id = cursor.lastrowid
            if data.answers:
                for a in data.answers:
                    cursor.execute(
                        """
                        INSERT INTO survey_answers (survey_id, question_id, answer_rating, answer_bool, answer_text, answer_number)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            int(new_id),
                            a.question_id,
                            a.answer_rating,
                            a.answer_bool,
                            a.answer_text,
                            a.answer_number,
                        ),
                    )
            conn.commit()
            return int(new_id)
        finally:
            if conn:
                conn.close()

    def get_survey_by_appointment(self, appointment_id: int) -> Optional[dict[str, object]]:
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn, dictionary=True)
            cursor.execute("SELECT * FROM surveys WHERE appointment_id = %s", (appointment_id,))
            return cursor.fetchone()
        finally:
            if conn: conn.close()

    def get_surveys(self) -> list[dict[str, object]]:
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn, dictionary=True)
            cursor.execute("SELECT * FROM surveys ORDER BY id DESC")
            return cursor.fetchall()
        finally:
            if conn: conn.close()

    # --- Preguntas de encuesta (configuración) ---

    def list_survey_questions(
        self,
        include_inactive: bool = False,
        contract_kind: Optional[str] = None,
    ) -> list[dict[str, object]]:
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn, dictionary=True)
            q = "SELECT * FROM survey_questions WHERE 1=1"
            params: list[object] = []
            if not include_inactive:
                q += " AND is_active = 1"
            if contract_kind is not None and str(contract_kind).strip():
                ck = str(contract_kind).strip().lower()
                if ck == "both":
                    q += " AND contract_kind = 'both'"
                else:
                    q += " AND (contract_kind = %s OR contract_kind = 'both')"
                    params.append(ck)
            q += " ORDER BY sort_order ASC, id ASC"
            cursor.execute(q, tuple(params))
            return cursor.fetchall()
        finally:
            if conn:
                conn.close()

    def get_survey_question(self, question_id: int) -> Optional[dict[str, object]]:
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn, dictionary=True)
            cursor.execute("SELECT * FROM survey_questions WHERE id = %s", (question_id,))
            return cursor.fetchone()
        finally:
            if conn:
                conn.close()

    def create_survey_question(self, data: SurveyQuestion) -> int:
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn)
            oj = json.dumps(data.options, ensure_ascii=False) if data.options else None
            cursor.execute(
                """
                INSERT INTO survey_questions (label, question_type, options_json, sort_order, contract_kind, is_active)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    data.label,
                    data.question_type,
                    oj,
                    data.sort_order,
                    str(data.contract_kind or "tattoo"),
                    1 if data.is_active else 0,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid or 0)
        finally:
            if conn:
                conn.close()

    def update_survey_question(self, data: SurveyQuestion) -> None:
        if data.id is None:
            raise ValueError("question id requerido")
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute(
                """
                UPDATE survey_questions
                SET label = %s, question_type = %s, options_json = %s, sort_order = %s,
                    contract_kind = %s, is_active = %s
                WHERE id = %s
                """,
                (
                    data.label,
                    data.question_type,
                    json.dumps(data.options, ensure_ascii=False) if data.options else None,
                    data.sort_order,
                    str(data.contract_kind or "tattoo"),
                    1 if data.is_active else 0,
                    data.id,
                ),
            )
            conn.commit()
        finally:
            if conn:
                conn.close()

    def delete_survey_question(self, question_id: int) -> None:
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute("DELETE FROM survey_questions WHERE id = %s", (question_id,))
            conn.commit()
        finally:
            if conn:
                conn.close()

    def count_survey_answers_for_question(self, question_id: int) -> int:
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute(
                "SELECT COUNT(*) FROM survey_answers WHERE question_id = %s",
                (question_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return 0
            return int(row[0])
        finally:
            if conn:
                conn.close()

    def get_survey_question_stats_summary(self) -> list[dict[str, object]]:
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn, dictionary=True)
            cursor.execute(
                """
                SELECT
                    q.id AS question_id,
                    q.label,
                    q.question_type,
                    q.sort_order,
                    COALESCE(q.contract_kind, 'tattoo') AS contract_kind,
                    q.is_active,
                    COUNT(a.id) AS response_count,
                    AVG(a.answer_rating) AS avg_rating,
                    SUM(CASE WHEN a.answer_bool IS NOT NULL AND a.answer_bool = 1 THEN 1 ELSE 0 END) AS yes_count,
                    SUM(CASE WHEN a.answer_bool IS NOT NULL AND a.answer_bool = 0 THEN 1 ELSE 0 END) AS no_count,
                    SUM(
                        CASE
                            WHEN a.answer_text IS NOT NULL AND CHAR_LENGTH(TRIM(a.answer_text)) > 0 THEN 1
                            ELSE 0
                        END
                    ) AS text_response_count,
                    AVG(a.answer_number) AS avg_number
                FROM survey_questions q
                LEFT JOIN survey_answers a ON a.question_id = q.id
                GROUP BY q.id, q.label, q.question_type, q.sort_order, q.contract_kind, q.is_active
                ORDER BY q.sort_order ASC, q.id ASC
                """
            )
            rows = cursor.fetchall()

            rating_breakdown: dict[int, dict[str, int]] = {}
            cursor.execute(
                """
                SELECT question_id, answer_rating AS rv, COUNT(*) AS cnt
                FROM survey_answers
                WHERE answer_rating IS NOT NULL
                GROUP BY question_id, answer_rating
                """
            )
            for r in cursor.fetchall():
                qid = int(r["question_id"])
                rv = int(r["rv"])
                rating_breakdown.setdefault(qid, {})[str(rv)] = int(r["cnt"])

            number_breakdown: dict[int, dict[str, int]] = {}
            cursor.execute(
                """
                SELECT question_id, answer_number AS nv, COUNT(*) AS cnt
                FROM survey_answers
                WHERE answer_number IS NOT NULL
                GROUP BY question_id, answer_number
                """
            )
            for r in cursor.fetchall():
                qid = int(r["question_id"])
                nv = r["nv"]
                key = format(float(nv), "g") if nv is not None else "0"
                number_breakdown.setdefault(qid, {})[key] = int(r["cnt"])

            choice_breakdown: dict[int, dict[str, int]] = {}
            cursor.execute(
                """
                SELECT a.question_id, a.answer_text AS txt, COUNT(*) AS cnt
                FROM survey_answers a
                INNER JOIN survey_questions q ON q.id = a.question_id
                WHERE q.question_type IN ('radio', 'select', 'checkbox')
                  AND a.answer_text IS NOT NULL
                  AND CHAR_LENGTH(TRIM(a.answer_text)) > 0
                GROUP BY a.question_id, a.answer_text
                """
            )
            for r in cursor.fetchall():
                qid = int(r["question_id"])
                txt = str(r["txt"] or "").strip()
                if not txt:
                    continue
                choice_breakdown.setdefault(qid, {})[txt] = int(r["cnt"])

            for row in rows:
                qid = int(row["question_id"])
                rb = rating_breakdown.get(qid)
                nb = number_breakdown.get(qid)
                cb = choice_breakdown.get(qid)
                row["rating_breakdown"] = rb if rb else None
                row["number_breakdown"] = nb if nb else None
                row["choice_breakdown"] = cb if cb else None
            return rows
        finally:
            if conn:
                conn.close()

    # --- Plantillas ---

    def create_template(self, data: ContractTemplate) -> int:
        """Crea una nueva plantilla de contrato en la base de datos.
        Si `is_active`, desactiva el resto de plantillas activas del mismo `contract_kind`.
        """
        with self.db.transaction() as conn:
            cursor = self._get_cursor(conn)
            query = """INSERT INTO contract_templates (name, contract_kind, version, content, is_active)
                       VALUES (%s, %s, %s, %s, %s)"""
            values = (data.name, data.contract_kind, data.version, data.content, data.is_active)
            cursor.execute(query, values)
            new_id = int(cursor.lastrowid or 0)
            if data.is_active and new_id:
                cursor.execute(
                    """UPDATE contract_templates SET is_active = 0
                       WHERE contract_kind = %s AND id != %s AND is_active = 1""",
                    (data.contract_kind, new_id),
                )
            return new_id

    def get_templates(
        self, only_active: bool = False, contract_kind: Optional[str] = None
    ) -> list[dict[str, object]]:
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn, dictionary=True)
            query = "SELECT * FROM contract_templates WHERE 1=1"
            params: list[object] = []
            if only_active:
                query += " AND is_active = TRUE"
            if contract_kind:
                query += " AND contract_kind = %s"
                params.append(contract_kind)
            query += " ORDER BY contract_kind ASC, name ASC, id DESC"
            if params:
                cursor.execute(query, tuple(params))
            else:
                cursor.execute(query)
            return cursor.fetchall()
        finally:
            if conn: conn.close()

    def get_template_by_id(self, template_id: int) -> Optional[ContractTemplate]:
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn, dictionary=True)
            cursor.execute("SELECT * FROM contract_templates WHERE id = %s", (template_id,))
            res = cursor.fetchone()
            if res:
                ck = res.get("contract_kind")
                if ck is None:
                    ck = "tattoo"
                return ContractTemplate(
                    id=res["id"],
                    name=res["name"],
                    version=res["version"],
                    content=res["content"],
                    contract_kind=str(ck),
                    is_active=bool(res["is_active"]),
                )
            return None
        finally:
            if conn: conn.close()

    def update_template(self, template_id: int, data: ContractTemplate) -> None:
        """Actualiza plantilla; si queda activa, desactiva las demás del mismo `contract_kind`."""
        with self.db.transaction() as conn:
            cursor = self._get_cursor(conn)
            cursor.execute(
                """UPDATE contract_templates
                   SET name = %s, contract_kind = %s, version = %s, content = %s, is_active = %s
                   WHERE id = %s""",
                (data.name, data.contract_kind, data.version, data.content, data.is_active, template_id),
            )
            if data.is_active:
                cursor.execute(
                    """UPDATE contract_templates SET is_active = 0
                       WHERE contract_kind = %s AND id != %s AND is_active = 1""",
                    (data.contract_kind, template_id),
                )

    def delete_template(self, template_id: int) -> None:
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute("DELETE FROM contract_templates WHERE id = %s", (template_id,))
            conn.commit()
        finally:
            if conn: conn.close()

    def get_detailed_report(self, start_date: str, end_date: str) -> list[dict[str, object]]:
        """Citas en rango de fechas con campos útiles para reporte financiero."""
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn, dictionary=True)
            cursor.execute(
                """
                SELECT id, customer_name, phone, service_type, appointment_date,
                       deposit, status, created_at
                FROM appointments
                WHERE DATE(appointment_date) BETWEEN DATE(%s) AND DATE(%s)
                ORDER BY appointment_date ASC
                """,
                (start_date, end_date),
            )
            return cursor.fetchall()
        finally:
            if conn: conn.close()