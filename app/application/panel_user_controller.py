"""Usuarios del panel: registro, login y gestión (CRUD lite)."""
from __future__ import annotations

import logging

from litestar import Controller, get, patch, post, put, status_codes
from litestar.datastructures import State
from litestar.exceptions import HTTPException

from app.schemas.common import MessageResponse
from app.schemas.panel_user import (
    PanelUserAssignable,
    PanelUserCreate,
    PanelUserLogin,
    PanelUserLoginResponse,
    PanelUserModulesBody,
    PanelUserPublic,
    PanelUserRegister,
    PanelUserRegisteredResponse,
    PanelUserUpdate,
)

logger = logging.getLogger(__name__)


class PanelUserController(Controller):
    path = "/api/panel-users"

    @get("/")
    async def list_panel_users(self, state: State) -> list[PanelUserPublic]:
        try:
            return await state.service.list_panel_users()
        except Exception as e:
            logger.exception("panel_user list")
            raise HTTPException(detail=str(e), status_code=500) from e

    @get("/assignable-for-appointments")
    async def list_assignable_for_appointments(self, state: State) -> list[PanelUserAssignable]:
        """Tatuadores y perforadores activos para asignar citas."""
        try:
            return await state.service.list_panel_users_assignable_for_appointments()
        except Exception as e:
            logger.exception("panel_user assignable")
            raise HTTPException(detail=str(e), status_code=500) from e

    @get("/{user_id:int}")
    async def get_panel_user(self, user_id: int, state: State) -> PanelUserPublic:
        try:
            row = await state.service.get_panel_user(user_id)
            if row is None:
                raise HTTPException(detail="Usuario no encontrado.", status_code=404)
            return row
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("panel_user get")
            raise HTTPException(detail=str(e), status_code=500) from e

    @post("/", status_code=status_codes.HTTP_201_CREATED)
    async def create_panel_user(self, data: PanelUserCreate, state: State) -> PanelUserRegisteredResponse:
        try:
            new_id = await state.service.create_panel_user(data)
            return PanelUserRegisteredResponse(message="Usuario creado.", id=new_id)
        except ValueError as e:
            if str(e) == "USERNAME_TAKEN":
                raise HTTPException(
                    detail="Ese nombre de usuario ya está en uso.",
                    status_code=status_codes.HTTP_409_CONFLICT,
                ) from e
            raise HTTPException(detail=str(e), status_code=400) from e
        except Exception as e:
            logger.exception("panel_user create")
            raise HTTPException(detail=str(e), status_code=500) from e

    @patch("/{user_id:int}")
    async def update_panel_user(
        self,
        user_id: int,
        data: PanelUserUpdate,
        state: State,
    ) -> MessageResponse:
        try:
            await state.service.update_panel_user(user_id, data)
            return MessageResponse(status="success", message="Usuario actualizado.")
        except ValueError as e:
            if str(e) == "EMPTY_UPDATE":
                raise HTTPException(detail="No hay campos para actualizar.", status_code=400) from e
            if str(e) == "USER_NOT_FOUND":
                raise HTTPException(detail="Usuario no encontrado.", status_code=404) from e
            raise HTTPException(detail=str(e), status_code=400) from e
        except Exception as e:
            logger.exception("panel_user patch")
            raise HTTPException(detail=str(e), status_code=500) from e

    @post("/register", status_code=status_codes.HTTP_201_CREATED)
    async def register(self, data: PanelUserRegister, state: State) -> PanelUserRegisteredResponse:
        try:
            new_id = await state.service.register_panel_user(data)
            return PanelUserRegisteredResponse(
                message="Usuario registrado.",
                id=new_id,
            )
        except ValueError as e:
            if str(e) == "USERNAME_TAKEN":
                raise HTTPException(
                    detail="Ese nombre de usuario ya está en uso.",
                    status_code=status_codes.HTTP_409_CONFLICT,
                ) from e
            raise HTTPException(detail=str(e), status_code=400) from e
        except Exception as e:
            logger.exception("panel_user register")
            raise HTTPException(detail=str(e), status_code=500) from e

    @get("/{user_id:int}/modules/effective")
    async def get_effective_modules(self, user_id: int, state: State) -> list[str]:
        try:
            return await state.service.get_effective_panel_module_keys(user_id)
        except ValueError as e:
            if str(e) == "USER_NOT_FOUND":
                raise HTTPException(detail="Usuario no encontrado.", status_code=404) from e
            raise HTTPException(detail=str(e), status_code=400) from e
        except Exception as e:
            logger.exception("panel_user modules effective")
            raise HTTPException(detail=str(e), status_code=500) from e

    @get("/{user_id:int}/modules")
    async def get_module_grants(self, user_id: int, state: State) -> list[str]:
        try:
            return await state.service.get_panel_user_module_grants_raw(user_id)
        except ValueError as e:
            if str(e) == "USER_NOT_FOUND":
                raise HTTPException(detail="Usuario no encontrado.", status_code=404) from e
            raise HTTPException(detail=str(e), status_code=400) from e
        except Exception as e:
            logger.exception("panel_user modules get")
            raise HTTPException(detail=str(e), status_code=500) from e

    @put("/{user_id:int}/modules")
    async def put_modules(
        self,
        user_id: int,
        data: PanelUserModulesBody,
        state: State,
    ) -> MessageResponse:
        try:
            await state.service.set_panel_user_modules(user_id, data)
            return MessageResponse(status="success", message="Permisos de módulos actualizados.")
        except ValueError as e:
            if str(e) == "USER_NOT_FOUND":
                raise HTTPException(detail="Usuario no encontrado.", status_code=404) from e
            if str(e) == "ADMIN_MODULES_FIXED":
                raise HTTPException(
                    detail="Los administradores tienen acceso completo; no se restringe por módulos.",
                    status_code=400,
                ) from e
            raise HTTPException(detail=str(e), status_code=400) from e
        except Exception as e:
            logger.exception("panel_user modules put")
            raise HTTPException(detail=str(e), status_code=500) from e

    @post("/login")
    async def login(self, data: PanelUserLogin, state: State) -> PanelUserLoginResponse:
        try:
            user = await state.service.login_panel_user_session(data.username, data.password)
            if user is None:
                raise HTTPException(
                    detail="Credenciales incorrectas.",
                    status_code=status_codes.HTTP_401_UNAUTHORIZED,
                )
            return PanelUserLoginResponse(message="Sesión válida.", user=user)
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("panel_user login")
            raise HTTPException(detail=str(e), status_code=500) from e
