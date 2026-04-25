from contextlib import contextmanager
from typing import Iterator

import mysql.connector
from mysql.connector import Error
from mysql.connector.connection import MySQLConnection


class DatabaseManager:
    """Gestiona la conexión física a MySQL."""
    def __init__(self, host, user, password, database):
        self.config = {
            'host': host,
            'user': user,
            'password': password,
            'database': database
        }

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