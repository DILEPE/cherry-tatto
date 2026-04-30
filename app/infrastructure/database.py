from contextlib import contextmanager
from typing import Iterator

import mysql.connector
from mysql.connector import Error
from mysql.connector.connection import MySQLConnection


class DatabaseManager:
    """Gestiona la conexión física a MySQL."""

    def __init__(self, host, user, password, database):
        self.config = {
            "host": host,
            "user": user,
            "password": password,
            "database": database,
        }

    def ensure_appointment_date_datetime(self) -> None:
        """Si `appointment_date` es tipo DATE, amplía a DATETIME para guardar hora de cita."""
        conn = self.get_connection()
        if conn is None:
            return
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'appointments'
                  AND COLUMN_NAME = 'appointment_date'
                """
            )
            row = cur.fetchone()
            if row and str(row[0]).lower() == "date":
                cur.execute("ALTER TABLE appointments MODIFY COLUMN appointment_date DATETIME")
                conn.commit()
                print("[DB] appointments.appointment_date → DATETIME")
        except Exception as e:
            print(f"[DB] Migración appointment_date omitida o ya aplicada: {e}")
        finally:
            conn.close()

    def ensure_appointment_is_priority_column(self) -> None:
        """Añade `is_priority` (BOOLEAN) si no existe, para marcar citas prioritarias en agenda."""
        conn = self.get_connection()
        if conn is None:
            return
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'appointments'
                  AND COLUMN_NAME = 'is_priority'
                """
            )
            row = cur.fetchone()
            if row and int(row[0]) == 0:
                cur.execute(
                    "ALTER TABLE appointments ADD COLUMN is_priority TINYINT(1) NOT NULL DEFAULT 0"
                )
                conn.commit()
                print("[DB] appointments.is_priority añadida")
        except Exception as e:
            print(f"[DB] Migración is_priority omitida o ya aplicada: {e}")
        finally:
            conn.close()

    def get_connection(self) -> MySQLConnection | None:
        try:
            return mysql.connector.connect(**self.config)
        except Error as e:
            print(f"Error conectando a MySQL: {e}")
            return None

    @contextmanager
    def transaction(self) -> Iterator[MySQLConnection]:
        """Context manager: una transacción (commit/rollback) por bloque."""
        conn = self.get_connection()
        if conn is None:
            raise ConnectionError("No se pudo establecer conexión con MySQL.")
        try:
            conn.autocommit = False
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()