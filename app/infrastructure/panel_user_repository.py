"""Persistencia de usuarios del panel (MySQL)."""
from __future__ import annotations

from typing import Any, Optional

from mysql.connector.connection import MySQLConnection


class PanelUserRepository:
    def __init__(self, db_manager):
        self.db = db_manager

    def get_by_username(
        self,
        username: str,
        conn: Optional[MySQLConnection] = None,
    ) -> Optional[dict[str, Any]]:
        own = conn is None
        if own:
            conn = self.db.get_connection()
        if conn is None:
            raise ConnectionError("No se pudo establecer conexión con MySQL.")
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT id, username, password_hash, is_active FROM panel_users WHERE username = %s",
                (username,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            if own and conn:
                conn.close()

    def insert(
        self,
        username: str,
        password_hash: str,
        conn: MySQLConnection,
    ) -> int:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO panel_users (username, password_hash)
            VALUES (%s, %s)
            """,
            (username, password_hash),
        )
        return int(cur.lastrowid)
