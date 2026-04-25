"""Persistence for customers (MySQL)."""
from __future__ import annotations

import json
import logging
from typing import Optional

from mysql.connector.connection import MySQLConnection

from app.schemas.customer import CustomerCreate, CustomerUpdate

logger = logging.getLogger(__name__)


class CustomerRepository:
    def __init__(self, db_manager):
        self.db = db_manager

    def _cursor(self, conn: MySQLConnection, dictionary: bool = False):
        return conn.cursor(dictionary=dictionary)

    def _row_to_dict(self, row: dict[str, object] | None) -> dict[str, object] | None:
        if row is None:
            return None
        out = dict(row)
        sm = out.get("social_media")
        if isinstance(sm, (bytes, str)) and sm:
            try:
                out["social_media"] = json.loads(sm) if isinstance(sm, str) else json.loads(sm.decode())
            except (json.JSONDecodeError, ValueError):
                out["social_media"] = None
        return out

    def get_by_id(self, customer_id: int, conn: Optional[MySQLConnection] = None) -> Optional[dict[str, object]]:
        own = conn is None
        if own:
            conn = self.db.get_connection()
        if conn is None:
            raise ConnectionError("No se pudo establecer conexión con MySQL.")
        try:
            cur = self._cursor(conn, dictionary=True)
            cur.execute(
                "SELECT * FROM customers WHERE id = %s AND deleted_at IS NULL",
                (customer_id,),
            )
            row = cur.fetchone()
            return self._row_to_dict(row) if row else None
        finally:
            if own and conn:
                conn.close()

    def get_by_document_number(
        self, document_number: str, conn: Optional[MySQLConnection] = None
    ) -> Optional[dict[str, object]]:
        own = conn is None
        if own:
            conn = self.db.get_connection()
        if conn is None:
            raise ConnectionError("No se pudo establecer conexión con MySQL.")
        try:
            cur = self._cursor(conn, dictionary=True)
            cur.execute(
                "SELECT * FROM customers WHERE document_number = %s AND deleted_at IS NULL",
                (document_number.strip(),),
            )
            row = cur.fetchone()
            return self._row_to_dict(row) if row else None
        finally:
            if own and conn:
                conn.close()

    def count_customers(
        self,
        *,
        search: Optional[str] = None,
        document_number: Optional[str] = None,
    ) -> int:
        conn = self.db.get_connection()
        if conn is None:
            raise ConnectionError("No se pudo establecer conexión con MySQL.")
        try:
            cur = self._cursor(conn, dictionary=True)
            where = ["deleted_at IS NULL"]
            params: list[object] = []
            if document_number:
                where.append("document_number = %s")
                params.append(document_number.strip())
            elif search and search.strip():
                term = f"%{search.strip()}%"
                where.append(
                    "(first_name LIKE %s OR last_name LIKE %s OR document_number LIKE %s OR email LIKE %s)"
                )
                params.extend([term, term, term, term])
            sql = f"SELECT COUNT(*) AS c FROM customers WHERE {' AND '.join(where)}"
            cur.execute(sql, tuple(params))
            row = cur.fetchone()
            return int(row["c"]) if row else 0
        finally:
            conn.close()

    def list_customers(
        self,
        *,
        limit: int,
        offset: int,
        search: Optional[str] = None,
        document_number: Optional[str] = None,
    ) -> list[dict[str, object]]:
        conn = self.db.get_connection()
        if conn is None:
            raise ConnectionError("No se pudo establecer conexión con MySQL.")
        try:
            cur = self._cursor(conn, dictionary=True)
            where = ["deleted_at IS NULL"]
            params: list[object] = []
            if document_number:
                where.append("document_number = %s")
                params.append(document_number.strip())
            elif search and search.strip():
                term = f"%{search.strip()}%"
                where.append(
                    "(first_name LIKE %s OR last_name LIKE %s OR document_number LIKE %s OR email LIKE %s)"
                )
                params.extend([term, term, term, term])
            sql = (
                f"SELECT * FROM customers WHERE {' AND '.join(where)} "
                "ORDER BY created_at DESC LIMIT %s OFFSET %s"
            )
            params.extend([limit, offset])
            cur.execute(sql, tuple(params))
            return [self._row_to_dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def _social_json(self, value: Optional[dict[str, object]]) -> Optional[str]:
        if value is None:
            return None
        return json.dumps(value)

    def insert(self, data: CustomerCreate, conn: MySQLConnection) -> int:
        cur = self._cursor(conn)
        sql = """
            INSERT INTO customers (
                first_name, last_name, birth_date, document_type, document_number,
                document_issue_date,
                email, phone_number, address, nationality, profession, secondary_email,
                social_media, emergency_contact_name, emergency_contact_phone,
                is_minor, guardian_name, guardian_document_type, guardian_document_number,
                guardian_document_issue_date
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            )
        """
        values: tuple[object, ...] = (
            data.first_name,
            data.last_name,
            data.birth_date,
            data.document_type,
            data.document_number.strip(),
            data.document_issue_date,
            str(data.email),
            data.phone_number,
            data.address,
            data.nationality,
            data.profession,
            str(data.secondary_email) if data.secondary_email else None,
            self._social_json(data.social_media),
            data.emergency_contact_name,
            data.emergency_contact_phone,
            data.is_minor,
            data.guardian_name,
            data.guardian_document_type,
            data.guardian_document_number,
            data.guardian_document_issue_date,
        )
        cur.execute(sql, values)
        new_id = cur.lastrowid
        logger.info("Customer created id=%s document=%s", new_id, data.document_number)
        return int(new_id)

    def update(self, customer_id: int, data: CustomerUpdate, conn: MySQLConnection) -> None:
        cur = self._cursor(conn)
        sql = """
            UPDATE customers SET
                first_name=%s, last_name=%s, birth_date=%s, document_type=%s, document_number=%s,
                document_issue_date=%s,
                email=%s, phone_number=%s, address=%s, nationality=%s, profession=%s, secondary_email=%s,
                social_media=%s, emergency_contact_name=%s, emergency_contact_phone=%s,
                is_minor=%s, guardian_name=%s, guardian_document_type=%s, guardian_document_number=%s,
                guardian_document_issue_date=%s
            WHERE id=%s AND deleted_at IS NULL
        """
        values: tuple[object, ...] = (
            data.first_name,
            data.last_name,
            data.birth_date,
            data.document_type,
            data.document_number.strip(),
            data.document_issue_date,
            str(data.email),
            data.phone_number,
            data.address,
            data.nationality,
            data.profession,
            str(data.secondary_email) if data.secondary_email else None,
            self._social_json(data.social_media),
            data.emergency_contact_name,
            data.emergency_contact_phone,
            data.is_minor,
            data.guardian_name,
            data.guardian_document_type,
            data.guardian_document_number,
            data.guardian_document_issue_date,
            customer_id,
        )
        cur.execute(sql, values)
        logger.info("Customer updated id=%s", customer_id)

    def soft_delete(self, customer_id: int, conn: Optional[MySQLConnection] = None) -> None:
        own = conn is None
        if own:
            conn = self.db.get_connection()
        if conn is None:
            raise ConnectionError("No se pudo establecer conexión con MySQL.")
        try:
            cur = self._cursor(conn)
            cur.execute(
                "UPDATE customers SET deleted_at = CURRENT_TIMESTAMP WHERE id = %s AND deleted_at IS NULL",
                (customer_id,),
            )
            if own:
                conn.commit()
            logger.info("Customer soft-deleted id=%s", customer_id)
        finally:
            if own and conn:
                conn.close()

    def upsert_by_document(self, data: CustomerCreate, conn: MySQLConnection) -> int:
        existing = self.get_by_document_number(data.document_number, conn)
        if existing:
            upd = CustomerUpdate(**data.model_dump())
            self.update(int(existing["id"]), upd, conn)
            return int(existing["id"])
        return self.insert(data, conn)
