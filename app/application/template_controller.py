from litestar import Controller, get, post, put, delete, status_codes
from litestar.datastructures import State
from litestar.exceptions import HTTPException
from app.domain.models import ContractTemplate, APIResponse
from typing import List

class TemplateController(Controller):
    """
    Controlador para la gestión del ciclo de vida de las plantillas de contrato.
    Permite el versionado y la administración de los textos legales (LONGTEXT).
    """
    path = "/api/templates"

    @get("/")
    async def list_templates(self, state: State, only_active: bool = False) -> List[ContractTemplate]:
        """Obtiene el listado de todas las plantillas disponibles."""
        try:
            return await state.service.get_templates(only_active=only_active)
        except Exception as e:
            raise HTTPException(detail=f"Error al listar plantillas: {str(e)}", status_code=500)

    @get("/{template_id:int}")
    async def get_template(self, state: State, template_id: int) -> ContractTemplate:
        """Obtiene el detalle de una plantilla específica por su ID."""
        template = await state.service.get_template_by_id(template_id)
        if not template:
            raise HTTPException(detail="Plantilla no encontrada", status_code=404)
        return template

    @post("/", status_code=status_codes.HTTP_201_CREATED)
    async def create_template(self, data: ContractTemplate, state: State) -> APIResponse:
        """Crea una nueva versión de plantilla de contrato."""
        try:
            new_id = await state.service.create_template(data)
            return APIResponse(
                status="success",
                message="Plantilla de contrato creada exitosamente",
                id=new_id
            )
        except Exception as e:
            raise HTTPException(detail=f"Error al crear plantilla: {str(e)}", status_code=500)

    @put("/{template_id:int}")
    async def update_template(self, template_id: int, data: ContractTemplate, state: State) -> APIResponse:
        """Actualiza una plantilla existente."""
        try:
            await state.service.update_template(template_id, data)
            return APIResponse(
                status="success",
                message=f"Plantilla {template_id} actualizada correctamente"
            )
        except Exception as e:
            raise HTTPException(detail=f"Error al actualizar plantilla: {str(e)}", status_code=500)

    @delete("/{template_id:int}", status_code=status_codes.HTTP_200_OK)
    async def delete_template(self, template_id: int, state: State) -> APIResponse:
        """Elimina una plantilla de la base de datos."""
        try:
            await state.service.delete_template(template_id)
            return APIResponse(
                status="success",
                message=f"Plantilla {template_id} eliminada exitosamente"
            )
        except Exception as e:
            raise HTTPException(detail=f"Error al eliminar plantilla: {str(e)}", status_code=500)
