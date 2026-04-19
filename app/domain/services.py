
import asyncio
from typing import Any
from app.domain.models import AppointmentCreate, ContractSign

class BusinessLogicService:
    """
    Capa de Dominio: Contiene la lógica central del estudio.
    Orquesta las operaciones entre los modelos, el repositorio y n8n.
    """
    def __init__(self, repository, notifier):
        self.repository = repository
        self.notifier = notifier

    async def register_appointment(self, data: AppointmentCreate) -> int:
        """
        Registra una nueva cita. 
        Al ser un objeto de modelo, accedemos con puntos (data.name).
        """
        # 1. Guardar en la base de datos
        new_id = self.repository.create(data)
        
        # 2. Notificar a n8n de forma asíncrona para no retrasar la API
        # Enviamos un evento de 'appointment_created'
        asyncio.create_task(self._async_notify("appointment_created", {
            "id": new_id,
            "name": data.name,
            "phone": data.phone,
            "service": data.service,
            "date": data.date
        }))
        
        return new_id

    async def process_contract_signature(self, data: ContractSign):
        """
        Procesa la firma del contrato y la encuesta de salud.
        """
        # 1. Verificar que la cita exista
        appointment = self.repository.get_by_id(data.appointment_id)
        if not appointment:
            raise ValueError(f"Cita con ID {data.appointment_id} no encontrada.")

        # 2. Guardar los datos del contrato en MySQL
        self.repository.create_contract(data)

        # 3. Actualizar el estado de la cita a 'Completado'
        self.repository.update_status(data.appointment_id, "Completado")
        
        # 4. Notificar a n8n para enviar cuidados y seguimiento
        # Aquí enviamos también el health_data para que n8n pueda procesar alertas si es necesario
        notification_payload = {
            "appointment_id": data.appointment_id,
            "customer_name": appointment.name,
            "phone": appointment.phone,
            "service": appointment.service,
            "health_summary": data.health_data
        }
        
        # Ejecutamos la notificación sin bloquear la respuesta al cliente
        asyncio.create_task(self._async_notify("contract_signed", notification_payload))

    async def _async_notify(self, event: str, payload: dict):
        """
        Helper para ejecutar la notificación a n8n sin bloquear el flujo principal.
        """
        try:
            loop = asyncio.get_event_loop()
            # Se ejecuta en un executor para no bloquear el bucle de eventos asíncrono
            await loop.run_in_executor(None, self.notifier.notify, event, payload)
        except Exception as e:
            # Importante loggear el error de la tarea asíncrona si falla
            print(f"Error en segundo plano al notificar n8n: {e}")