from typing import List, Dict, Any, Optional

from app.domain.models import AppointmentCreate

class AppointmentRepository:
    """Capa de persistencia: Solo conoce SQL."""
    def __init__(self, db_manager):
        self.db = db_manager

    def get_all(self) -> List[AppointmentCreate]:
        conn = self.db.get_connection()
        if not conn: return []
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM appointments ORDER BY created_at DESC")
        res = cursor.fetchall()
        cursor.close()
        conn.close()
        return res

    def create(self, data: AppointmentCreate) -> int:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        query = """INSERT INTO appointments 
                   (customer_name, phone, service_type, detail, appointment_date, deposit) 
                   VALUES (%s, %s, %s, %s, %s, %s)"""
    
        # CAMBIO AQUÍ: Usar notación de punto (.)
        values = (
            data.name, 
            data.phone, 
            data.service, 
            data.detail or '', 
            data.date, 
            data.deposit or 0
        )
    
        cursor.execute(query, values)
        new_id = cursor.lastrowid
        conn.commit()
        cursor.close()
        conn.close()
        return new_id


    def get_by_id(self, appointment_id: int) -> Optional[AppointmentCreate]:
        conn = self.db.get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM appointments WHERE id = %s", (appointment_id,))
        res = cursor.fetchone()
        cursor.close()
        conn.close()
        if res:
            return AppointmentCreate(
                name=res['customer_name'],
                phone=res['phone'],
                service=res['service_type'],
                detail=res.get('detail', ''),
                date=res.get('appointment_date'),
                deposit=res.get('deposit', 0)
            )
        return None

    def update_status(self, appointment_id: int, status: str):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE appointments SET status = %s WHERE id = %s", (status, appointment_id))
        conn.commit()
        cursor.close()
        conn.close()

        def create_contract(self, data: ContractSign) -> int:
            """Guarda la firma y la encuesta de salud (NUEVO MÉTODO)."""
            conn = self.db.get_connection()
            try:
                cursor = self._get_cursor(conn)
                # Serializamos el diccionario de salud a JSON string
                health_json = json.dumps(data.health_data)
            
                query = """INSERT INTO contracts 
                           (appointment_id, is_minor, health_data, client_signature, tutor_signature) 
                           VALUES (%s, %s, %s, %s, %s)"""
            
                values = (
                    data.appointment_id,
                    data.is_minor,
                    health_json,
                    data.signature,
                    data.tutor_signature
                )
            
                cursor.execute(query, values)
                contract_id = cursor.lastrowid
                conn.commit()
                return contract_id
            finally:
                if conn: conn.close()