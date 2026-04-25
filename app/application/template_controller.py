from __future__ import annotations

from litestar import Controller, delete, get, post, put, status_codes
from litestar.datastructures import State
from litestar.exceptions import HTTPException

from app.schemas.common import ApiSuccessResponse
from app.schemas.template import (
    ContractTemplateCreate,
    ContractTemplateRead,
    ContractTemplateUpdate,
)


class TemplateController(Controller):
    """
    Controlador para la gestión del ciclo de vida de las plantillas de contrato.
    """
    path = "/api/templates"

    @get("/")
    async def list_templates(
        self, state: State, only_active: bool = False
    ) -> list[ContractTemplateRead]:
        """Obtiene el listado de todas las plantillas disponibles."""
        try:
            return await state.service.get_templates(only_active=only_active)
        except Exception as e:
            raise HTTPException(detail=f"Error al listar plantillas: {str(e)}", status_code=500) from e

    @get("/{template_id:int}")
    async def get_template(self, state: State, template_id: int) -> ContractTemplateRead:
        """Obtiene el detalle de una plantilla específica por su ID."""
        template = await state.service.get_template_by_id(template_id)
        if not template:
            raise HTTPException(detail="Plantilla no encontrada", status_code=404)
        return template

    @post("/", status_code=status_codes.HTTP_201_CREATED)
    async def create_template(
        self, data: ContractTemplateCreate, state: State
    ) -> ApiSuccessResponse:
        """Crea una nueva versión de plantilla de contrato."""
        try:
            new_id = await state.service.create_template(data)
            return ApiSuccessResponse(
                status="success",
                message="Plantilla de contrato creada exitosamente",
                id=new_id,
            )
        except Exception as e:
            raise HTTPException(detail=f"Error al crear plantilla: {str(e)}", status_code=500) from e

    @put("/{template_id:int}")
    async def update_template(
        self, template_id: int, data: ContractTemplateUpdate, state: State
    ) -> ApiSuccessResponse:
        """Actualiza una plantilla existente."""
        try:
            await state.service.update_template(template_id, data)
            return ApiSuccessResponse(
                status="success",
                message=f"Plantilla {template_id} actualizada correctamente",
            )
        except Exception as e:
            raise HTTPException(
                detail=f"Error al actualizar plantilla: {str(e)}", status_code=500
            ) from e

    @delete("/{template_id:int}", status_code=status_codes.HTTP_200_OK)
    async def delete_template(self, template_id: int, state: State) -> ApiSuccessResponse:
        """Elimina una plantilla de la base de datos."""
        try:
            await state.service.delete_template(template_id)
            return ApiSuccessResponse(
                status="success",
                message=f"Plantilla {template_id} eliminada exitosamente",
            )
        except Exception as e:
            raise HTTPException(
                detail=f"Error al eliminar plantilla: {str(e)}", status_code=500
            ) from e
