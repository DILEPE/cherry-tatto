"""Registro e inicio de sesión de operadores del panel (sin JWT; validación para Streamlit)."""
from __future__ import annotations

import logging

from litestar import Controller, post, status_codes
from litestar.datastructures import State
from litestar.exceptions import HTTPException

from app.schemas.common import MessageResponse
from app.schemas.panel_user import PanelUserLogin, PanelUserRegister, PanelUserRegisteredResponse

logger = logging.getLogger(__name__)


class PanelUserController(Controller):
    path = "/api/panel-users"

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

    @post("/login")
    async def login(self, data: PanelUserLogin, state: State) -> MessageResponse:
        try:
            ok = await state.service.verify_panel_user_login(data.username, data.password)
            if not ok:
                raise HTTPException(
                    detail="Credenciales incorrectas.",
                    status_code=status_codes.HTTP_401_UNAUTHORIZED,
                )
            return MessageResponse(status="success", message="Sesión válida.")
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("panel_user login")
            raise HTTPException(detail=str(e), status_code=500) from e
