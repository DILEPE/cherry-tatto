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
                """
                SELECT id, username, first_name, last_name, address, phone, store, role,
                       password_hash, is_active
                FROM panel_users
                WHERE username = %s
                """,
                (username,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            if own and conn:
                conn.close()

    def get_by_id(
        self,
        user_id: int,
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
                """
                SELECT id, username, first_name, last_name, address, phone, store, role,
                       password_hash, is_active, created_at, updated_at
                FROM panel_users
                WHERE id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            if own and conn:
                conn.close()

    def list_public_rows(
        self,
        conn: Optional[MySQLConnection] = None,
    ) -> list[dict[str, Any]]:
        own = conn is None
        if own:
            conn = self.db.get_connection()
        if conn is None:
            raise ConnectionError("No se pudo establecer conexión con MySQL.")
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT id, username, first_name, last_name, address, phone, store, role,
                       is_active, created_at, updated_at
                FROM panel_users
                ORDER BY id ASC
                """
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows] if rows else []
        finally:
            if own and conn:
                conn.close()

    def list_assignable_for_appointments(
        self,
        conn: Optional[MySQLConnection] = None,
    ) -> list[dict[str, Any]]:
        own = conn is None
        if own:
            conn = self.db.get_connection()
        if conn is None:
            raise ConnectionError("No se pudo establecer conexión con MySQL.")
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """
                SELECT id, username, first_name, last_name, role
                FROM panel_users
                WHERE is_active = 1 AND role IN ('tatuador', 'perforador')
                ORDER BY role ASC, id ASC
                """
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows] if rows else []
        finally:
            if own and conn:
                conn.close()

    def insert(
        self,
        *,
        username: str,
        password_hash: str,
        first_name: str,
        last_name: str,
        address: Optional[str],
        phone: Optional[str],
        store: str,
        role: str,
        is_active: bool,
        conn: MySQLConnection,
    ) -> int:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO panel_users (
                username, first_name, last_name, address, phone, store, role,
                password_hash, is_active
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                username,
                first_name,
                last_name,
                address,
                phone,
                store,
                role,
                password_hash,
                is_active,
            ),
        )
        return int(cur.lastrowid)

    _UPDATE_ALLOWED = frozenset(
        {
            "first_name",
            "last_name",
            "address",
            "phone",
            "store",
            "role",
            "is_active",
            "password_hash",
        }
    )

    def update(
        self,
        user_id: int,
        fields: dict[str, Any],
        conn: MySQLConnection,
    ) -> None:
        sets: list[str] = []
        values: list[Any] = []
        for key, val in fields.items():
            if key not in self._UPDATE_ALLOWED:
                continue
            sets.append(f"{key} = %s")
            values.append(val)
        if not sets:
            return
        values.append(user_id)
        cur = conn.cursor()
        cur.execute(
            f"UPDATE panel_users SET {', '.join(sets)} WHERE id = %s",
            tuple(values),
        )

    def list_module_keys_for_user(
        self,
        user_id: int,
        conn: Optional[MySQLConnection] = None,
    ) -> list[str]:
        own = conn is None
        if own:
            conn = self.db.get_connection()
        if conn is None:
            raise ConnectionError("No se pudo establecer conexión con MySQL.")
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT module_key FROM panel_user_module_access
                WHERE user_id = %s
                ORDER BY module_key
                """,
                (user_id,),
            )
            return [str(r[0]) for r in cur.fetchall()]
        finally:
            if own and conn:
                conn.close()

    def replace_module_keys(
        self,
        user_id: int,
        keys: list[str],
        conn: MySQLConnection,
    ) -> None:
        cur = conn.cursor()
        cur.execute("DELETE FROM panel_user_module_access WHERE user_id = %s", (user_id,))
        for k in keys:
            cur.execute(
                "INSERT INTO panel_user_module_access (user_id, module_key) VALUES (%s, %s)",
                (user_id, k),
            )
