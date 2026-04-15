from typing import Dict, Any, List
from litestar import Controller, get, post, status_codes
from litestar.exceptions import HTTPException

class AppointmentController(Controller):
    path = "/api/appointments"

    @get()
    async def list_all(self, state: Any) -> List[Dict[str, Any]]:
        """Lista todas las citas registradas."""
        try:
            # Accedemos al repositorio a través del servicio o directamente si es necesario
            # En arquitectura limpia, el controlador pide al servicio los datos
            return state.service.repository.get_all()
        except Exception as e:
            raise HTTPException(detail=f"Error al obtener citas: {str(e)}", status_code=500)

    @post(status_code=status_codes.HTTP_201_CREATED)
    async def create(self, data: Dict[str, Any], state: Any) -> Dict[str, Any]:
        """
        Crea una nueva cita. 
        Si el vendedor la crea desde la tablet, se dispara la confirmación en n8n.
        """
        try:
            service = state.service
            new_id = await service.register_appointment(data)
            return {
                "id": new_id,
                "status": "success",
                "message": "Cita creada y notificación enviada a n8n"
            }
        except Exception as e:
            raise HTTPException(detail=f"Error al crear cita: {str(e)}", status_code=400)