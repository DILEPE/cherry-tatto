from typing import List, Dict, Any, Optional

class AppointmentRepository:
    """Capa de persistencia: Solo conoce SQL."""
    def __init__(self, db_manager):
        self.db = db_manager

    def get_all(self) -> List[Dict[str, Any]]:
        conn = self.db.get_connection()
        if not conn: return []
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM appointments ORDER BY created_at DESC")
        res = cursor.fetchall()
        cursor.close()
        conn.close()
        return res

    def create(self, data: Dict[str, Any]) -> int:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        query = """INSERT INTO appointments 
                   (customer_name, phone, service_type, detail, appointment_date, deposit) 
                   VALUES (%s, %s, %s, %s, %s, %s)"""
        values = (data['name'], data['phone'], data['service'], 
                  data.get('detail', ''), data.get('date'), data.get('deposit', 0))
        cursor.execute(query, values)
        new_id = cursor.lastrowid
        conn.commit()
        cursor.close()
        conn.close()
        return new_id

    def get_by_id(self, appointment_id: int) -> Optional[Dict[str, Any]]:
        conn = self.db.get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM appointments WHERE id = %s", (appointment_id,))
        res = cursor.fetchone()
        cursor.close()
        conn.close()
        return res

    def update_status(self, appointment_id: int, status: str):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE appointments SET status = %s WHERE id = %s", (status, appointment_id))
        conn.commit()
        cursor.close()
        conn.close()