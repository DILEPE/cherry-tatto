from litestar import Controller, get, post, status_codes
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
            msg = str(e)
            status_code404 = status_codes.HTTP_404_NOT_FOUND
            status_code400 = status_codes.HTTP_400_BAD_REQUEST
            code = status_code404 if "no encontrada" in msg.lower() else status_code400
            raise HTTPException(detail=msg, status_code=code) from e
        except Exception as e:
            raise HTTPException(
                detail=f"Error al procesar contrato: {str(e)}", status_code=500
            ) from e

    @get("/customer/{customer_id:int}")
    async def list_by_customer(self, customer_id: int, state: State) -> list[dict]:
        try:
            return await state.service.list_contracts_by_customer(customer_id)
        except Exception as e:
            raise HTTPException(detail=f"Error al listar contratos: {str(e)}", status_code=500) from e

    @get("/{contract_id:int}")
    async def get_contract(self, contract_id: int, state: State) -> dict:
        try:
            row = await state.service.get_contract(contract_id)
            if row is None:
                raise HTTPException(detail="Contrato no encontrado", status_code=404)
            return row
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(detail=f"Error al obtener contrato: {str(e)}", status_code=500) from e
