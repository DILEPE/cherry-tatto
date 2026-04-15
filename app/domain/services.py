import asyncio
from typing import Dict, Any

class BusinessLogicService:
    """Capa de Dominio: Contiene las reglas del estudio."""
    def __init__(self, repository, notifier):
        self.repository = repository
        self.notifier = notifier

    async def register_appointment(self, data: Dict[str, Any]):
        # Lógica: Crear en DB y avisar a n8n
        new_id = self.repository.create(data)
        
        # Disparar evento a n8n sin bloquear el flujo
        asyncio.create_task(self.notifier.notify("appointment_created", {
            "id": new_id, "name": data['name'], "phone": data['phone']
        }))
        return new_id

    async def process_contract_signature(self, data: Dict[str, Any]):
        appointment = self.repository.get_by_id(data['appointment_id'])
        if not appointment:
            raise ValueError("La cita no existe")

        # Regla: Cambiar estado a Completado tras firma
        self.repository.update_status(data['appointment_id'], "Completado")
        
        # Disparar evento a n8n para seguimientos de 8 días/meses
        asyncio.create_task(self.notifier.notify("contract_signed", {
            "name": appointment['customer_name'],
            "phone": appointment['phone'],
            "service": appointment['service_type']
        }))