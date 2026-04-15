import mysql.connector
from mysql.connector import Error

class DatabaseManager:
    """Gestiona la conexión física a MySQL."""
    def __init__(self, host, user, password, database):
        self.config = {
            'host': host,
            'user': user,
            'password': password,
            'database': database
        }

    def get_connection(self):
        try:
            return mysql.connector.connect(**self.config)
        except Error as e:
            print(f"Error conectando a MySQL: {e}")
            return None