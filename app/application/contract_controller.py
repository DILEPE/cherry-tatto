from litestar import Controller, post, status_codes
from litestar.datastructures import State
from litestar.exceptions import HTTPException

from app.schemas.common import ApiSuccessResponse
from app.schemas.contract import ContractSignRequest, contract_sign_to_domain


class ContractController(Controller):
    path = "/api/contracts"

    @post(status_code=status_codes.HTTP_201_CREATED)
    async def process_contract(self, data: ContractSignRequest, state: State) -> ApiSuccessResponse:
        """
        Punto de entrada para la firma de contratos.
        El cuerpo se valida con Pydantic (`ContractSignRequest`).
        """
        try:
            await state.service.process_contract_signature(contract_sign_to_domain(data))
            return ApiSuccessResponse(
                status="success",
                message="Contrato firmado. n8n iniciará los flujos de seguimiento.",
            )
        except ValueError as e:
            raise HTTPException(detail=str(e), status_code=404) from e
        except Exception as e:
            raise HTTPException(
                detail=f"Error al procesar contrato: {str(e)}", status_code=500
            ) from e
