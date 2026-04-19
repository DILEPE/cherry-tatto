from litestar import Controller, post, status_codes
from litestar.datastructures import State
from litestar.exceptions import HTTPException
from app.domain.models import ContractSign, APIResponse

class ContractController(Controller):
    path = "/api/contracts"

    @post(status_code=status_codes.HTTP_201_CREATED)
    async def process_contract(self, data: ContractSign, state: State) -> APIResponse:
        """
        Punto de entrada para la firma de contratos. 
        Litestar valida automáticamente que 'data' cumpla con el modelo ContractSign.
        """
        try:
            service = state.service
            await service.process_contract_signature(data)
            
            return APIResponse(
                status="success",
                message="Contrato firmado. n8n iniciará los flujos de seguimiento."
            )
        except ValueError as e:
            raise HTTPException(detail=str(e), status_code=404)
        except Exception as e:
            raise HTTPException(detail=f"Error al procesar contrato: {str(e)}", status_code=500)