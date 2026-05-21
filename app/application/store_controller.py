"""HTTP routes: catálogo de tiendas."""

from __future__ import annotations

import logging

from litestar import Controller, delete, get, post, put, status_codes
from litestar.datastructures import State
from litestar.exceptions import HTTPException
from litestar.params import Parameter

from app.schemas.common import MessageResponse
from app.schemas.store import StoreCreate, StoreCreatedResponse, StorePublic, StoreUpdate

logger = logging.getLogger(__name__)


class StoreController(Controller):
    path = "/api/stores"

    @get("/")
    async def list_stores(
        self,
        state: State,
        include_inactive: bool = Parameter(default=False, query="include_inactive"),
    ) -> list[StorePublic]:
        try:
            return await state.service.list_stores(include_inactive=include_inactive)
        except Exception as e:
            logger.exception("list_stores")
            raise HTTPException(detail=str(e), status_code=500) from e

    @get("/{store_id:int}")
    async def get_store(self, store_id: int, state: State) -> StorePublic:
        try:
            row = await state.service.get_store(store_id)
            if row is None:
                raise HTTPException(detail="Tienda no encontrada.", status_code=404)
            return row
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("get_store")
            raise HTTPException(detail=str(e), status_code=500) from e

    @post("/", status_code=status_codes.HTTP_201_CREATED)
    async def create_store(self, data: StoreCreate, state: State) -> StoreCreatedResponse:
        try:
            new_id = await state.service.create_store(data)
            return StoreCreatedResponse(id=new_id, message="Tienda creada correctamente.")
        except ValueError as e:
            raise HTTPException(detail=str(e), status_code=400) from e
        except Exception as e:
            logger.exception("create_store")
            raise HTTPException(detail=str(e), status_code=500) from e

    @put("/{store_id:int}")
    async def update_store(self, store_id: int, data: StoreUpdate, state: State) -> MessageResponse:
        try:
            await state.service.update_store(store_id, data)
            return MessageResponse(status="success", message="Tienda actualizada.")
        except ValueError as e:
            if str(e) == "STORE_NOT_FOUND":
                raise HTTPException(detail="Tienda no encontrada.", status_code=404) from e
            raise HTTPException(detail=str(e), status_code=400) from e
        except Exception as e:
            logger.exception("update_store")
            raise HTTPException(detail=str(e), status_code=500) from e

    @delete("/{store_id:int}", status_code=status_codes.HTTP_200_OK)
    async def delete_store(self, store_id: int, state: State) -> MessageResponse:
        try:
            await state.service.soft_delete_store(store_id)
            return MessageResponse(status="success", message="Tienda eliminada del catálogo.")
        except ValueError as e:
            msg = str(e)
            if msg == "STORE_NOT_FOUND":
                raise HTTPException(detail="Tienda no encontrada.", status_code=404) from e
            if msg == "STORE_IN_USE":
                raise HTTPException(
                    detail="No se puede eliminar: hay usuarios del panel asignados a esta tienda.",
                    status_code=400,
                ) from e
            raise HTTPException(detail=str(e), status_code=400) from e
        except Exception as e:
            logger.exception("delete_store")
            raise HTTPException(detail=str(e), status_code=500) from e
