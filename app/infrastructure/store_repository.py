"""Persistencia del catálogo de tiendas (MySQL)."""

from __future__ import annotations

from typing import Optional

from mysql.connector.connection import MySQLConnection


class StoreRepository:
    def __init__(self, db_manager) -> None:
        self.db = db_manager

    def _cursor(self, conn: MySQLConnection, dictionary: bool = False):
        return conn.cursor(dictionary=dictionary)

    def list_stores(self, *, include_inactive: bool = False) -> list[dict[str, object]]:
        conn = self.db.get_connection()
        if conn is None:
            raise ConnectionError("No se pudo establecer conexión con MySQL.")
        try:
            cur = self._cursor(conn, dictionary=True)
            where = "deleted_at IS NULL"
            if not include_inactive:
                where += " AND is_active = 1"
            cur.execute(
                f"""
                SELECT id, name, address, phone, email, is_active, created_at, updated_at
                FROM stores
                WHERE {where}
                ORDER BY name ASC
                """
            )
            return list(cur.fetchall() or [])
        finally:
            conn.close()

    def get_by_id(self, store_id: int) -> Optional[dict[str, object]]:
        conn = self.db.get_connection()
        if conn is None:
            raise ConnectionError("No se pudo establecer conexión con MySQL.")
        try:
            cur = self._cursor(conn, dictionary=True)
            cur.execute(
                """
                SELECT id, name, address, phone, email, is_active, created_at, updated_at
                FROM stores WHERE id = %s AND deleted_at IS NULL
                """,
                (int(store_id),),
            )
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def count_users_with_store_id(self, store_id: int) -> int:
        conn = self.db.get_connection()
        if conn is None:
            raise ConnectionError("No se pudo establecer conexión con MySQL.")
        try:
            cur = self._cursor(conn, dictionary=True)
            cur.execute(
                "SELECT COUNT(*) AS c FROM panel_users WHERE store_id = %s",
                (int(store_id),),
            )
            row = cur.fetchone()
            return int(row["c"]) if row else 0
        finally:
            conn.close()

    def insert(
        self,
        *,
        name: str,
        address: Optional[str],
        phone: Optional[str],
        email: Optional[str],
        is_active: bool,
        conn: Optional[MySQLConnection] = None,
    ) -> int:
        own = conn is None
        if own:
            conn = self.db.get_connection()
        if conn is None:
            raise ConnectionError("No se pudo establecer conexión con MySQL.")
        try:
            cur = self._cursor(conn)
            cur.execute(
                """
                INSERT INTO stores (name, address, phone, email, is_active)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    name.strip(),
                    (address or "").strip() or None,
                    (phone or "").strip() or None,
                    (email or "").strip() or None,
                    1 if is_active else 0,
                ),
            )
            if own:
                conn.commit()
            return int(cur.lastrowid or 0)
        except Exception:
            if own and conn:
                conn.rollback()
            raise
        finally:
            if own and conn:
                conn.close()

    def update(
        self,
        store_id: int,
        *,
        name: str,
        address: Optional[str],
        phone: Optional[str],
        email: Optional[str],
        is_active: bool,
    ) -> None:
        conn = self.db.get_connection()
        if conn is None:
            raise ConnectionError("No se pudo establecer conexión con MySQL.")
        try:
            cur = self._cursor(conn)
            cur.execute(
                """
                UPDATE stores
                SET name = %s, address = %s, phone = %s, email = %s, is_active = %s
                WHERE id = %s AND deleted_at IS NULL
                """,
                (
                    name.strip(),
                    (address or "").strip() or None,
                    (phone or "").strip() or None,
                    (email or "").strip() or None,
                    1 if is_active else 0,
                    int(store_id),
                ),
            )
            if cur.rowcount == 0:
                raise ValueError("STORE_NOT_FOUND")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def soft_delete(self, store_id: int) -> None:
        conn = self.db.get_connection()
        if conn is None:
            raise ConnectionError("No se pudo establecer conexión con MySQL.")
        try:
            cur = self._cursor(conn)
            cur.execute(
                "UPDATE stores SET deleted_at = CURRENT_TIMESTAMP, is_active = 0 WHERE id = %s AND deleted_at IS NULL",
                (int(store_id),),
            )
            if cur.rowcount == 0:
                raise ValueError("STORE_NOT_FOUND")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
