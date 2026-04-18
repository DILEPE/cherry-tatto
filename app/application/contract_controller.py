from typing import Dict, Any
from litestar import Controller, post, status_codes
from litestar.exceptions import HTTPException
from litestar.datastructures import State
from app.domain.models import ContractSign
from app.domain.models import APIResponse

class ContractController(Controller):
    """
    Controlador encargado de la gestión de contratos digitales.
    Maneja la recepción de encuestas, firmas y validaciones de menores.
    """
    path = "/api/contracts"

    @post(status_code=status_codes.HTTP_201_CREATED)
    async def process_contract(self, data: ContractSign, state: State) -> APIResponse:
        """
        Punto de entrada para procesar la firma de un contrato desde la Tablet.
        
        Se espera que el cuerpo de la petición (data) contenga:
        - appointment_id: Referencia a la cita en la base de datos (int).
        - is_minor: Booleano para activar lógica de documentos de tutor.
        - health_data: Resultados de la encuesta dinámica (dict).
        - signature: Firma del cliente en formato Base64 o string.
        - tutor_signature: Firma del acudiente (si aplica).
        - document_photos: Lista de fotos de los documentos con sello (si es menor).
        """
        try:
            # Recuperamos el servicio de negocio del estado global de la aplicación
            service = state.service
            
            # Delegamos el procesamiento a la capa de dominio (Logic Service)
            # Esto dispara la actualización en MySQL y los eventos en n8n
            await service.process_contract_signature(data)
            
            return APIResponse(
                status="success", 
                message="Contrato procesado y flujos de n8n activados"
            )       
        except ValueError as e:
            # Error de negocio (ej. la cita especificada no existe en la BD)
            raise HTTPException(detail=str(e), status_code=404)
        except Exception as e:
            # Errores técnicos inesperados
            raise HTTPException(detail=f"Error interno al procesar el contrato: {str(e)}", status_code=500)
