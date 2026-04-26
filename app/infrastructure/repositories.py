import json
from typing import Any, Optional
from app.domain.models import AppointmentCreate, ContractSign, ContractTemplate, Survey
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

    def get_all(self) -> list[dict[str, object]]:
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn, dictionary=True)
            cursor.execute("SELECT * FROM appointments ORDER BY created_at DESC")
            return cursor.fetchall()
        finally:
            if conn: conn.close()

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
            try:
                query = """INSERT INTO appointments
                           (customer_id, customer_name, phone, service_type, detail, appointment_date, deposit, total_amount, pending_balance, customer_credit, status)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                values = (
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
                    "Agendada",
                )
                cursor.execute(query, values)
            except Exception as e:
                # Compatibilidad temporal mientras se ejecuta la migración financiera.
                if "Unknown column 'total_amount'" not in str(e):
                    raise
                query_legacy = """INSERT INTO appointments
                                  (customer_id, customer_name, phone, service_type, detail, appointment_date, deposit, status)
                                  VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""
                values_legacy = (
                    customer_id,
                    data.name,
                    data.phone,
                    service_type,
                    data.detail or "",
                    data.date,
                    data.deposit or 0,
                    "Agendada",
                )
                cursor.execute(query_legacy, values_legacy)
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

    def cancel_appointment_with_credit(self, appointment_id: int) -> None:
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute(
                """
                UPDATE appointments
                SET status = 'Cancelada',
                    customer_credit = COALESCE(deposit, 0),
                    pending_balance = 0
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
        """Persiste la encuesta de satisfacción en la base de datos."""
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn)
            query = """
                INSERT INTO surveys (appointment_id, rating, comments, would_recommend)
                VALUES (%s, %s, %s, %s)
            """
            cursor.execute(query, (
                data.appointment_id,
                data.rating,
                data.comments,
                data.would_recommend
            ))
            new_id = cursor.lastrowid
            conn.commit()
            return new_id
        finally:
            if conn: conn.close()

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

    # --- Plantillas ---

    def create_template(self, data: ContractTemplate) -> int:
        """Crea una nueva plantilla de contrato en la base de datos."""
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn)
            query = """INSERT INTO contract_templates (name, version, content, is_active) 
                       VALUES (%s, %s, %s, %s)"""
            values = (data.name, data.version, data.content, data.is_active)
            cursor.execute(query, values)
            new_id = cursor.lastrowid
            conn.commit()
            return new_id
        finally:
            if conn: conn.close()

    def get_templates(self, only_active: bool = False) -> list[dict[str, object]]:
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn, dictionary=True)
            query = "SELECT * FROM contract_templates"
            if only_active:
                query += " WHERE is_active = TRUE"
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
                return ContractTemplate(
                    id=res['id'],
                    name=res['name'],
                    version=res['version'],
                    content=res['content'],
                    is_active=bool(res['is_active'])
                )
            return None
        finally:
            if conn: conn.close()

    def update_template(self, template_id: int, data: ContractTemplate) -> None:
        conn = self.db.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute(
                """UPDATE contract_templates
                   SET name = %s, version = %s, content = %s, is_active = %s
                   WHERE id = %s""",
                (data.name, data.version, data.content, data.is_active, template_id),
            )
            conn.commit()
        finally:
            if conn: conn.close()

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