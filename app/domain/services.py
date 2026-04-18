import asyncio
from typing import Any
from app.domain.models import AppointmentCreate, ContractSign

class BusinessLogicService:
    """Capa de Dominio: Contiene las reglas del estudio con tipado fuerte."""
    def __init__(self, repository, notifier):
        self.repository = repository
        self.notifier = notifier

    async def register_appointment(self, data: AppointmentCreate):
        """
        Registra una cita usando el modelo AppointmentCreate.
        El objeto 'data' es una Dataclass, por lo que se accede con puntos (.).
        """
        # IMPORTANTE: El repositorio ya recibe el objeto AppointmentCreate.
        # Se debe asegurar que el repositorio use data.name y no data['name'].
        new_id = self.repository.create(data)
        
        # Estructuramos el payload para n8n usando notación de punto (.)
        notification_payload = {
            "id": new_id, 
            "name": data.name, 
            "phone": data.phone,
            "service": data.service,
            "date": data.date,
            "deposit": data.deposit,
            "detail": data.detail
        }
        
        # Disparar evento a n8n sin bloquear el flujo principal
        asyncio.create_task(self._async_notify("appointment_created", notification_payload))
        
        return new_id

    async def process_contract_signature(self, data: ContractSign):
        """
        Procesa la firma del contrato usando el modelo ContractSign.
        """
        # Verificamos existencia de la cita antes de proceder.
        # El repositorio get_by_id ahora devuelve un objeto AppointmentCreate o None.
        appointment = self.repository.get_by_id(data.appointment_id)
        if not appointment:
            raise ValueError(f"La cita con ID {data.appointment_id} no existe")

        # Guardar los datos del contrato en MySQL pasando el objeto tipado
        self.repository.create_contract(data)

        # Regla de Negocio: Cambiar estado a 'Completado' tras la firma exitosa
        self.repository.update_status(data.appointment_id, "Completado")
        
        # Payload para n8n: Información para disparar flujos de post-venta
        notification_payload = {
            "appointment_id": data.appointment_id,
            "customer_name": appointment.name,
            "phone": appointment.phone,
            "service": appointment.service,
            "is_minor": data.is_minor,
            "health_summary": data.health_data
        }
        
        asyncio.create_task(self._async_notify("contract_signed", notification_payload))

    async def _async_notify(self, event: str, payload: dict):
        """Ejecuta la notificación a n8n en un hilo separado para optimizar tiempos de respuesta."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.notifier.notify, event, payload)