import json
import re
from datetime import date, datetime
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

    @staticmethod
    def _appointment_datetime_sql_string(val: object) -> str:
        """Serializa valor MySQL DATE/DATETIME a texto estable para capas superiores (PDF, API)."""
        if val is None:
            return ""
        if isinstance(val, datetime):
            return val.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(val, date):
            return f"{val.strftime('%Y-%m-%d')} 09:00:00"
        return str(val).strip()

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
                        EXISTS (
                            SELECT 1 FROM contracts c
                            WHERE c.appointment_id = a.id
                              AND (
                                  c.artist_signature IS NULL
                                  OR CHAR_LENGTH(TRIM(c.artist_signature)) < 80
                              )
                        ) AS contract_pending_artist_signature,
                        pu.username AS assigned_username,
                        pu.first_name AS assigned_first_name,
                        pu.last_name AS assigned_last_name,
                        pu.role AS assigned_role,
                        pu.store_id AS assigned_store_id
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
                        EXISTS (
                            SELECT 1 FROM contracts c
                            WHERE c.appointment_id = a.id
                              AND (
                                  c.artist_signature IS NULL
                                  OR CHAR_LENGTH(TRIM(c.artist_signature)) < 80
                              )
                        ) AS contract_pending_artist_signature,
                        pu.username AS assigned_username,
                        pu.first_name AS assigned_first_name,
                        pu.last_name AS assigned_last_name,
                        pu.role AS assigned_role,
                        pu.store_id AS assigned_store_id
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
                rawp = row.get("contract_pending_artist_signature")
                row["contract_pending_artist_signature"] = bool(rawp) if rawp is not None else False
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

    def get_appointment_list_row(self, appointment_id: int) -> Optional[dict[str, object]]:
        """Una fila con el mismo shape que `get_all` (join con panel_users si existe la columna)."""
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn, dictionary=True)
            try:
                cursor.execute(
                    """
                    SELECT a.*,
                        EXISTS (SELECT 1 FROM contracts c WHERE c.appointment_id = a.id)
                            AS has_signed_contract,
                        EXISTS (
                            SELECT 1 FROM contracts c
                            WHERE c.appointment_id = a.id
                              AND (
                                  c.artist_signature IS NULL
                                  OR CHAR_LENGTH(TRIM(c.artist_signature)) < 80
                              )
                        ) AS contract_pending_artist_signature,
                        pu.username AS assigned_username,
                        pu.first_name AS assigned_first_name,
                        pu.last_name AS assigned_last_name,
                        pu.role AS assigned_role,
                        pu.store_id AS assigned_store_id
                    FROM appointments a
                    LEFT JOIN panel_users pu ON pu.id = a.assigned_panel_user_id
                    WHERE a.id = %s
                    LIMIT 1
                    """,
                    (appointment_id,),
                )
            except Exception as e:
                err = str(e)
                if (
                    "Unknown column 'a.assigned_panel_user_id'" in err
                    or "Unknown column 'assigned_panel_user_id'" in err
                ):
                    cursor.execute(
                        """
                        SELECT a.*,
                            EXISTS (SELECT 1 FROM contracts c WHERE c.appointment_id = a.id)
                                AS has_signed_contract,
                            EXISTS (
                                SELECT 1 FROM contracts c
                                WHERE c.appointment_id = a.id
                                  AND (
                                      c.artist_signature IS NULL
                                      OR CHAR_LENGTH(TRIM(c.artist_signature)) < 80
                                  )
                            ) AS contract_pending_artist_signature
                        FROM appointments a
                        WHERE a.id = %s
                        LIMIT 1
                        """,
                        (appointment_id,),
                    )
                else:
                    raise
            row = cursor.fetchone()
            if not row:
                return None
            raw = row.get("has_signed_contract")
            row["has_signed_contract"] = bool(raw) if raw is not None else False
            rawp = row.get("contract_pending_artist_signature")
            row["contract_pending_artist_signature"] = bool(rawp) if rawp is not None else False
            return row
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
                        AS has_signed_contract,
                    EXISTS (
                        SELECT 1 FROM contracts c
                        WHERE c.appointment_id = a.id
                          AND (
                              c.artist_signature IS NULL
                              OR CHAR_LENGTH(TRIM(c.artist_signature)) < 80
                          )
                    ) AS contract_pending_artist_signature
                FROM appointments a
                ORDER BY a.created_at DESC
                """
            )
            rows = cursor.fetchall()
            for row in rows:
                raw = row.get("has_signed_contract")
                row["has_signed_contract"] = bool(raw) if raw is not None else False
                rawp = row.get("contract_pending_artist_signature")
                row["contract_pending_artist_signature"] = bool(rawp) if rawp is not None else False
            return rows
        finally:
            if conn:
                conn.close()

    def _appointment_list_select_sql(self) -> str:
        return """
            SELECT a.*,
                EXISTS (SELECT 1 FROM contracts c WHERE c.appointment_id = a.id)
                    AS has_signed_contract,
                EXISTS (
                    SELECT 1 FROM contracts c
                    WHERE c.appointment_id = a.id
                      AND (
                          c.artist_signature IS NULL
                          OR CHAR_LENGTH(TRIM(c.artist_signature)) < 80
                      )
                ) AS contract_pending_artist_signature,
                pu.username AS assigned_username,
                pu.first_name AS assigned_first_name,
                pu.last_name AS assigned_last_name,
                pu.role AS assigned_role,
                pu.store_id AS assigned_store_id,
                (
                    SELECT CONCAT(a.id, '-', LPAD(MOD(apr.id, 100), 2, '0'))
                    FROM appointment_payment_receipts apr
                    WHERE apr.appointment_id = a.id
                    ORDER BY apr.id DESC
                    LIMIT 1
                ) AS receipt_label
            FROM appointments a
            LEFT JOIN panel_users pu ON pu.id = a.assigned_panel_user_id
        """

    def _search_where_clause(
        self,
        field: str,
        term: str,
    ) -> tuple[str, list[object]]:
        """Devuelve fragmento SQL `WHERE ...` y parámetros (sin incluir filtros de asignado)."""
        f = (field or "name").strip().lower()
        raw = (term or "").strip()
        if not raw:
            raise ValueError("SEARCH_TERM_EMPTY")

        if f == "name":
            like = f"%{raw}%"
            clause = """
                (
                    a.customer_name LIKE %s
                    OR EXISTS (
                        SELECT 1 FROM customers c
                        WHERE c.id = a.customer_id
                          AND CONCAT(TRIM(c.first_name), ' ', TRIM(c.last_name)) LIKE %s
                    )
                )
            """
            return clause, [like, like]

        if f == "document":
            doc = re.sub(r"\s+", "", raw)
            like = f"%{doc}%"
            clause = """
                EXISTS (
                    SELECT 1 FROM customers c
                    WHERE c.id = a.customer_id
                      AND REPLACE(REPLACE(c.document_number, ' ', ''), '.', '') LIKE %s
                )
            """
            return clause, [like]

        if f == "receipt":
            params: list[object] = []
            parts: list[str] = []
            m = re.match(r"^(\d+)\s*-\s*(\d+)$", raw)
            if m:
                appt_id = int(m.group(1))
                rec_tail = int(m.group(2))
                parts.append(
                    """
                    EXISTS (
                        SELECT 1 FROM appointment_payment_receipts apr
                        WHERE apr.appointment_id = a.id
                          AND a.id = %s
                          AND (apr.id = %s OR MOD(apr.id, 100) = %s)
                    )
                    """
                )
                params.extend([appt_id, rec_tail, rec_tail])
            if raw.isdigit():
                n = int(raw)
                parts.append(
                    """
                    (
                        a.id = %s
                        OR EXISTS (
                            SELECT 1 FROM appointment_payment_receipts apr
                            WHERE apr.appointment_id = a.id AND apr.id = %s
                        )
                    )
                    """
                )
                params.extend([n, n])
            like = f"%{raw}%"
            parts.append(
                """
                EXISTS (
                    SELECT 1 FROM appointment_payment_receipts apr
                    WHERE apr.appointment_id = a.id
                      AND (
                          CAST(apr.id AS CHAR) LIKE %s
                          OR apr.file_name LIKE %s
                          OR CONCAT(a.id, '-', apr.id) LIKE %s
                      )
                )
                """
            )
            params.extend([like, like, like])
            return "(" + " OR ".join(parts) + ")", params

        raise ValueError("SEARCH_FIELD_INVALID")

    def search_appointments(
        self,
        *,
        field: str,
        term: str,
        limit: int = 10,
        offset: int = 0,
        assigned_panel_user_id: Optional[int] = None,
    ) -> tuple[list[dict[str, object]], int]:
        where_search, params = self._search_where_clause(field, term)
        clauses = [where_search]
        all_params: list[object] = list(params)
        if assigned_panel_user_id is not None:
            clauses.append("a.assigned_panel_user_id = %s")
            all_params.append(int(assigned_panel_user_id))
        where_sql = " AND ".join(f"({c})" for c in clauses)
        base_from = self._appointment_list_select_sql()
        lim = max(1, min(int(limit), 50))
        off = max(0, int(offset))

        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn, dictionary=True)
            try:
                cursor.execute(
                    f"SELECT COUNT(DISTINCT a.id) AS c FROM appointments a WHERE {where_sql}",
                    tuple(all_params),
                )
                total_row = cursor.fetchone() or {}
                total = int(total_row.get("c") or 0)
                cursor.execute(
                    f"""
                    {base_from}
                    WHERE {where_sql}
                    ORDER BY a.appointment_date DESC, a.id DESC
                    LIMIT %s OFFSET %s
                    """,
                    tuple(all_params) + (lim, off),
                )
                rows = cursor.fetchall()
            except Exception as e:
                err = str(e)
                if "Unknown column 'pu.store_id'" in err:
                    cursor.execute(
                        f"""
                        SELECT a.*,
                            EXISTS (SELECT 1 FROM contracts c WHERE c.appointment_id = a.id)
                                AS has_signed_contract,
                            EXISTS (
                                SELECT 1 FROM contracts c
                                WHERE c.appointment_id = a.id
                                  AND (
                                      c.artist_signature IS NULL
                                      OR CHAR_LENGTH(TRIM(c.artist_signature)) < 80
                                  )
                            ) AS contract_pending_artist_signature,
                            pu.username AS assigned_username,
                            pu.first_name AS assigned_first_name,
                            pu.last_name AS assigned_last_name,
                            pu.role AS assigned_role,
                            (
                                SELECT CONCAT(a.id, '-', LPAD(MOD(apr.id, 100), 2, '0'))
                                FROM appointment_payment_receipts apr
                                WHERE apr.appointment_id = a.id
                                ORDER BY apr.id DESC
                                LIMIT 1
                            ) AS receipt_label
                        FROM appointments a
                        LEFT JOIN panel_users pu ON pu.id = a.assigned_panel_user_id
                        WHERE {where_sql}
                        ORDER BY a.appointment_date DESC, a.id DESC
                        LIMIT %s OFFSET %s
                        """,
                        tuple(all_params) + (lim, off),
                    )
                    rows = cursor.fetchall()
                    cursor.execute(
                        f"SELECT COUNT(DISTINCT a.id) AS c FROM appointments a WHERE {where_sql}",
                        tuple(all_params),
                    )
                    total_row = cursor.fetchone() or {}
                    total = int(total_row.get("c") or 0)
                elif (
                    "appointment_payment_receipts" in err
                    or "Unknown column 'a.assigned_panel_user_id'" in err
                ):
                    return [], 0
                else:
                    raise
            for row in rows:
                raw = row.get("has_signed_contract")
                row["has_signed_contract"] = bool(raw) if raw is not None else False
                rawp = row.get("contract_pending_artist_signature")
                row["contract_pending_artist_signature"] = (
                    bool(rawp) if rawp is not None else False
                )
                if not row.get("receipt_label"):
                    row["receipt_label"] = None
            return rows, total
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
                    id=res["id"],
                    name=(res.get("customer_name") or "") or "",
                    phone=(res.get("phone") or "") or "",
                    service=(res.get("service_type") or "") or "",
                    service_type=(res.get("service_type") or "") or "",
                    date=self._appointment_datetime_sql_string(res.get("appointment_date")),
                    status=res.get("status"),
                    deposit=float(res.get("deposit") or 0),
                    total_amount=float(res.get("total_amount") or 0),
                    pending_balance=float(res.get("pending_balance") or 0),
                    customer_id=res.get("customer_id"),
                    detail=(res.get("detail") or "") or "",
                )
            return None
        finally:
            if conn: conn.close()

    def get_row_for_payment_receipt(self, appointment_id: int) -> Optional[Any]:
        """Cita + datos de cliente para PDF de recibo (nombre/teléfono/correo)."""
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn, dictionary=True)
            cursor.execute(
                """
                SELECT
                    a.id,
                    a.customer_id,
                    a.customer_name,
                    a.phone,
                    a.service_type,
                    a.detail,
                    a.appointment_date,
                    a.deposit,
                    a.total_amount,
                    a.pending_balance,
                    a.status,
                    c.first_name AS customer_first_name,
                    c.last_name AS customer_last_name,
                    c.phone_number AS customer_phone_number,
                    c.email AS customer_email
                FROM appointments a
                LEFT JOIN customers c
                    ON c.id = a.customer_id AND c.deleted_at IS NULL
                WHERE a.id = %s
                """,
                (appointment_id,),
            )
            res = cursor.fetchone()
            if not res:
                return None
            from types import SimpleNamespace

            cust_name = (
                f"{str(res.get('customer_first_name') or '').strip()} "
                f"{str(res.get('customer_last_name') or '').strip()}"
            ).strip()
            appt_name = str(res.get("customer_name") or "").strip()
            appt_phone = str(res.get("phone") or "").strip()
            cust_phone = str(res.get("customer_phone_number") or "").strip()
            return SimpleNamespace(
                id=res["id"],
                name=appt_name or cust_name,
                phone=appt_phone or cust_phone,
                service=(res.get("service_type") or "") or "",
                service_type=(res.get("service_type") or "") or "",
                date=self._appointment_datetime_sql_string(res.get("appointment_date")),
                status=res.get("status"),
                deposit=float(res.get("deposit") or 0),
                total_amount=float(res.get("total_amount") or 0),
                pending_balance=float(res.get("pending_balance") or 0),
                customer_id=res.get("customer_id"),
                detail=(res.get("detail") or "") or "",
                customer_email=str(res.get("customer_email") or "").strip(),
            )
        finally:
            if conn:
                conn.close()

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

    def get_latest_contract_row_for_appointment(self, appointment_id: int) -> Optional[dict[str, object]]:
        """Último contrato de la cita (mayor id)."""
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn, dictionary=True)
            cursor.execute(
                """
                SELECT id, appointment_id, template_id, is_minor, contract_text,
                       client_signature, tutor_signature, artist_signature
                FROM contracts
                WHERE appointment_id = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (int(appointment_id),),
            )
            return cursor.fetchone()
        finally:
            if conn:
                conn.close()

    def update_contract_artist_signature(self, contract_id: int, artist_signature: str) -> None:
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute(
                "UPDATE contracts SET artist_signature = %s WHERE id = %s",
                (artist_signature, int(contract_id)),
            )
            conn.commit()
        finally:
            if conn:
                conn.close()

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

    def patch_appointment_meta(
        self,
        appointment_id: int,
        *,
        is_priority: bool,
        assigned_panel_user_id: Optional[int] = None,
        detail: Optional[str] = None,
    ) -> None:
        """Actualiza prioridad siempre y, opcionalmente, profesional asignado o detalle."""
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn)
            clauses: list[str] = ["is_priority = %s"]
            params: list[object] = [1 if is_priority else 0]
            if assigned_panel_user_id is not None:
                clauses.append("assigned_panel_user_id = %s")
                params.append(assigned_panel_user_id)
            if detail is not None:
                clauses.append("detail = %s")
                params.append(detail)
            params.append(appointment_id)
            cursor.execute(
                f"UPDATE appointments SET {', '.join(clauses)} WHERE id = %s",
                tuple(params),
            )
            conn.commit()
        finally:
            if conn:
                conn.close()

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
                SELECT id, appointment_id, amount, note, paid_on, created_at
                FROM appointment_payments
                WHERE appointment_id = %s
                ORDER BY COALESCE(paid_on, DATE(created_at)) ASC, created_at ASC, id ASC
                """,
                (appointment_id,),
            )
            return cursor.fetchall()
        finally:
            if conn:
                conn.close()

    def create_payment(
        self,
        appointment_id: int,
        amount: float,
        note: Optional[str] = None,
        paid_on: Optional[date] = None,
    ) -> int:
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute(
                """
                INSERT INTO appointment_payments (appointment_id, amount, note, paid_on)
                VALUES (%s, %s, %s, %s)
                """,
                (appointment_id, amount, note, paid_on),
            )
            new_pid = int(cursor.lastrowid or 0)
            cursor.execute(
                """
                UPDATE appointments
                SET deposit = (@_new_dep := COALESCE(deposit, 0) + %s),
                    pending_balance = GREATEST(COALESCE(total_amount, 0) - @_new_dep, 0)
                WHERE id = %s
                """,
                (amount, appointment_id),
            )
            conn.commit()
            return new_pid
        finally:
            if conn:
                conn.close()

    def sync_appointment_deposit_totals_from_payments(self, appointment_id: int) -> None:
        """Recalcula deposit/pending desde la suma real de appointment_payments."""
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn, dictionary=False)
            cursor.execute(
                """
                SELECT COALESCE(SUM(amount), 0)
                FROM appointment_payments
                WHERE appointment_id = %s
                """,
                (appointment_id,),
            )
            r1 = cursor.fetchone()
            paid_sum = float(r1[0] or 0) if r1 else 0.0
            cursor.execute(
                "SELECT COALESCE(total_amount, 0) FROM appointments WHERE id = %s",
                (appointment_id,),
            )
            r2 = cursor.fetchone()
            total_amount = float(r2[0] or 0) if r2 else 0.0
            dep = round(paid_sum, 2)
            pending = round(max(total_amount - dep, 0.0), 2)
            cursor.execute(
                """
                UPDATE appointments
                SET deposit = %s,
                    pending_balance = %s
                WHERE id = %s
                """,
                (dep, pending, appointment_id),
            )
            conn.commit()
        finally:
            if conn:
                conn.close()

    def get_payment_by_id(self, payment_id: int) -> Optional[dict[str, object]]:
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn, dictionary=True)
            cursor.execute(
                "SELECT id, appointment_id, amount, note, paid_on, created_at FROM appointment_payments WHERE id = %s",
                (int(payment_id),),
            )
            row = cursor.fetchone()
            return row if isinstance(row, dict) else None
        finally:
            if conn:
                conn.close()

    def patch_payment_row(
        self,
        payment_id: int,
        *,
        amount: Optional[float] = None,
        note: Any = "__NO_NOTE_CHANGE__",
        paid_on: Any = "__NO_PAID_CHANGE__",
    ) -> int:
        """Devuelve appointment_id tras actualizar montos/metadata del abono y sincronizar totales."""
        row = self.get_payment_by_id(payment_id)
        if not row:
            raise ValueError("Abono no encontrado")
        appt_id = int(row["appointment_id"])
        parts: list[str] = []
        vals: list[object] = []
        if amount is not None:
            parts.append("amount = %s")
            vals.append(float(amount))
        if note != "__NO_NOTE_CHANGE__":
            parts.append("note = %s")
            vals.append(note)
        if paid_on != "__NO_PAID_CHANGE__":
            parts.append("paid_on = %s")
            vals.append(paid_on)
        if not parts:
            self.sync_appointment_deposit_totals_from_payments(appt_id)
            return appt_id
        vals.append(int(payment_id))
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn)
            sql_set = ", ".join(parts)
            cursor.execute(f"UPDATE appointment_payments SET {sql_set} WHERE id = %s", tuple(vals))
            conn.commit()
        finally:
            if conn:
                conn.close()
        self.sync_appointment_deposit_totals_from_payments(appt_id)
        return appt_id

    def insert_payment_ledger_row_only(
        self, appointment_id: int, amount: float, note: Optional[str] = None
    ) -> int:
        """Solo escribe el historial en appointment_payments; no modifica deposit ni pending_balance.
        El abono ya debe estar reflejado en la fila de la cita (p. ej. create() con deposit inicial)."""
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
            new_pid = int(cursor.lastrowid or 0)
            conn.commit()
            return new_pid
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

    def get_piercing_type_labels_by_appointment_ids(
        self,
        appointment_ids: list[int],
        *,
        question_id: int = 3,
    ) -> dict[int, str]:
        """Respuesta de encuesta «tipo de perforación» por cita (pregunta id 3 por defecto)."""
        ids = sorted({int(x) for x in appointment_ids if int(x) > 0})
        if not ids:
            return {}
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn, dictionary=True)
            placeholders = ",".join(["%s"] * len(ids))
            cursor.execute(
                f"""
                SELECT s.appointment_id, sa.answer_text
                FROM surveys s
                INNER JOIN survey_answers sa ON sa.survey_id = s.id
                WHERE s.appointment_id IN ({placeholders})
                  AND sa.question_id = %s
                  AND sa.answer_text IS NOT NULL
                  AND TRIM(sa.answer_text) <> ''
                """,
                (*ids, int(question_id)),
            )
            out: dict[int, str] = {}
            for row in cursor.fetchall() or []:
                try:
                    appt_id = int(row.get("appointment_id") or 0)
                except (TypeError, ValueError):
                    continue
                if appt_id <= 0 or appt_id in out:
                    continue
                raw = row.get("answer_text")
                if raw is None:
                    continue
                t = str(raw).strip()
                if t:
                    out[appt_id] = t
            return out
        finally:
            if conn:
                conn.close()

    def get_survey_answer_text(self, appointment_id: int, question_id: int) -> Optional[str]:
        """Texto en `survey_answers` (p. ej. opción elegida en radio/select)."""
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn, dictionary=True)
            cursor.execute(
                """
                SELECT sa.answer_text
                FROM surveys s
                INNER JOIN survey_answers sa ON sa.survey_id = s.id
                WHERE s.appointment_id = %s AND sa.question_id = %s
                LIMIT 1
                """,
                (int(appointment_id), int(question_id)),
            )
            row = cursor.fetchone()
            if not row:
                return None
            raw = row.get("answer_text")
            if raw is None:
                return None
            t = str(raw).strip()
            return t if t else None
        finally:
            if conn:
                conn.close()

    def get_procedure_consent_document(self, survey_option_label: str) -> Optional[dict[str, object]]:
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn, dictionary=True)
            cursor.execute(
                """
                SELECT survey_option_label, source_filename, pdf_base64
                FROM procedure_consent_documents
                WHERE survey_option_label = %s
                LIMIT 1
                """,
                (survey_option_label,),
            )
            return cursor.fetchone()
        finally:
            if conn:
                conn.close()

    def list_procedure_consent_labels(self) -> list[str]:
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn, dictionary=True)
            cursor.execute(
                """
                SELECT survey_option_label
                FROM procedure_consent_documents
                WHERE survey_option_label IS NOT NULL AND TRIM(survey_option_label) <> ''
                ORDER BY survey_option_label
                """
            )
            rows = cursor.fetchall() or []
            return [
                str(r["survey_option_label"]).strip()
                for r in rows
                if r.get("survey_option_label") and str(r["survey_option_label"]).strip()
            ]
        finally:
            if conn:
                conn.close()

    def list_survey_answer_texts_for_appointment(self, appointment_id: int) -> list[str]:
        """Textos de respuesta guardados para la cita (p. ej. radio/select/checkbox como JSON)."""
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn, dictionary=True)
            cursor.execute(
                """
                SELECT sa.answer_text
                FROM surveys s
                INNER JOIN survey_answers sa ON sa.survey_id = s.id
                WHERE s.appointment_id = %s
                  AND sa.answer_text IS NOT NULL
                  AND TRIM(sa.answer_text) <> ''
                ORDER BY sa.question_id ASC, sa.id ASC
                """,
                (int(appointment_id),),
            )
            out: list[str] = []
            for r in cursor.fetchall() or []:
                raw = r.get("answer_text")
                if raw is None:
                    continue
                s = str(raw).strip()
                if s:
                    out.append(s)
            return out
        finally:
            if conn:
                conn.close()

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
            cursor.execute(
                "SELECT COUNT(*) FROM contracts WHERE template_id = %s",
                (template_id,),
            )
            row = cursor.fetchone()
            used = int(row[0]) if row else 0
            if used > 0:
                raise ValueError("TEMPLATE_IN_USE")
            cursor.execute("DELETE FROM contract_templates WHERE id = %s", (template_id,))
            if cursor.rowcount == 0:
                raise ValueError("TEMPLATE_NOT_FOUND")
            conn.commit()
        except Exception:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()

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

    # --- Recibos de pago (PDF) ---

    def insert_payment_receipt(
        self,
        appointment_id: int,
        customer_id: Optional[int],
        appointment_payment_id: Optional[int],
        kind: str,
        amount: float,
        total_amount_snapshot: float,
        deposit_after: float,
        pending_after: float,
        note: Optional[str],
        file_name: str,
        pdf_bytes: bytes,
    ) -> int:
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute(
                """
                INSERT INTO appointment_payment_receipts (
                    appointment_id, customer_id, appointment_payment_id, kind,
                    amount, total_amount_snapshot, deposit_after, pending_after,
                    note, file_name, pdf
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    appointment_id,
                    customer_id,
                    appointment_payment_id,
                    kind,
                    float(amount),
                    float(total_amount_snapshot),
                    float(deposit_after),
                    float(pending_after),
                    note,
                    file_name,
                    pdf_bytes,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid or 0)
        finally:
            if conn:
                conn.close()

    def link_payment_receipt_to_payment(
        self,
        receipt_id: int,
        appointment_id: int,
        appointment_payment_id: int,
    ) -> bool:
        """Vincula un recibo existente a una fila de appointment_payments (p. ej. abono inicial)."""
        if receipt_id <= 0 or appointment_id <= 0 or appointment_payment_id <= 0:
            return False
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute(
                """
                UPDATE appointment_payment_receipts
                SET appointment_payment_id = %s
                WHERE id = %s
                  AND appointment_id = %s
                  AND (appointment_payment_id IS NULL OR appointment_payment_id = 0)
                """,
                (int(appointment_payment_id), int(receipt_id), int(appointment_id)),
            )
            conn.commit()
            return bool(cursor.rowcount)
        finally:
            if conn:
                conn.close()

    def list_payment_receipts_by_appointment(self, appointment_id: int) -> list[dict[str, object]]:
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn, dictionary=True)
            cursor.execute(
                """
                SELECT id, appointment_id, customer_id, appointment_payment_id, kind,
                       amount, total_amount_snapshot, deposit_after, pending_after,
                       note, file_name, created_at
                FROM appointment_payment_receipts
                WHERE appointment_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (appointment_id,),
            )
            return cursor.fetchall()
        finally:
            if conn:
                conn.close()

    def get_payment_receipt_for_resend(
        self, appointment_id: int, receipt_id: int
    ) -> Optional[dict[str, object]]:
        """Metadatos + PDF para reenviar el recibo por n8n."""
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn, dictionary=True)
            cursor.execute(
                """
                SELECT id, appointment_id, customer_id, appointment_payment_id, kind,
                       amount, note, file_name, pdf
                FROM appointment_payment_receipts
                WHERE id = %s AND appointment_id = %s
                LIMIT 1
                """,
                (receipt_id, appointment_id),
            )
            row = cursor.fetchone()
            return row if isinstance(row, dict) else None
        finally:
            if conn:
                conn.close()

    def get_payment_receipt_file(self, appointment_id: int, receipt_id: int) -> Optional[dict[str, object]]:
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn, dictionary=True)
            cursor.execute(
                """
                SELECT id, appointment_id, file_name, pdf
                FROM appointment_payment_receipts
                WHERE id = %s AND appointment_id = %s
                LIMIT 1
                """,
                (receipt_id, appointment_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return row
        finally:
            if conn:
                conn.close()
