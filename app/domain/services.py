import asyncio
from typing import Any, Dict, List, Optional

from app.domain.models import (
    AppointmentCreate,
    ContractSign,
    ContractTemplate,
    Survey,
)


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

    async def register_survey(self, data: Survey) -> int:
        """
        Registra la encuesta y alerta si la calificación es baja (1-2).
        """
        new_id = self.repository.create_survey(data)
        
        if data.rating <= 2:
            asyncio.create_task(self._async_notify("survey_low_rating", {
                "appointment_id": data.appointment_id,
                "rating": data.rating,
                "comments": data.comments
            }))
            
        return new_id

    async def get_survey_by_appointment(self, appointment_id: int) -> Optional[Dict[str, Any]]:
        return self.repository.get_survey_by_appointment(appointment_id)

    # --- Gestión de Plantillas ---
    async def get_templates(self, only_active: bool = False) -> List[ContractTemplate]:
        rows = self.repository.get_templates(only_active)
        return [self._template_row_to_model(row) for row in rows]

    async def get_template_by_id(self, template_id: int) -> Optional[ContractTemplate]:
        return self.repository.get_template_by_id(template_id)

    async def create_template(self, data: ContractTemplate) -> int:
        """Crea una nueva versión de plantilla de contrato."""
        return self.repository.create_template(data)

    async def update_template(self, template_id: int, data: ContractTemplate):
        return self.repository.update_template(template_id, data)

    async def delete_template(self, template_id: int):
        return self.repository.delete_template(template_id)

    # --- Reportes Financieros ---
    async def get_financial_report(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """Obtiene datos detallados para el reporte de Andrés."""
        return self.repository.get_detailed_report(start_date, end_date)

    async def list_appointments(self) -> List[Dict[str, Any]]:
        return self.repository.get_all()

    async def list_surveys(self) -> List[Dict[str, Any]]:
        return self.repository.get_surveys()

    @staticmethod
    def _template_row_to_model(row: Dict[str, Any]) -> ContractTemplate:
        return ContractTemplate(
            id=row["id"],
            name=row["name"],
            version=row["version"],
            content=row["content"],
            is_active=bool(row["is_active"]),
        )

    # --- Helpers Asíncronos ---
    async def _async_notify(self, event: str, payload: dict):
        """
        Ejecuta la notificación a n8n en un executor para no bloquear el event loop.
        """
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.notifier.notify, event, payload)
        except Exception as e:
            print(f"Error en segundo plano al notificar n8n: {e}")
