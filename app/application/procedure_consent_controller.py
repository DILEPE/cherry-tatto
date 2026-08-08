"""HTTP: catálogo de tipos de piercing / PDF de cuidados (procedure_consent_documents)."""

from __future__ import annotations

import logging
from urllib.parse import unquote

from litestar import Controller, delete, get, post, put, status_codes
from litestar.datastructures import State
from litestar.exceptions import HTTPException
from litestar.params import Parameter

from app.schemas.common import MessageResponse
from app.schemas.procedure_consent import (
    ProcedureConsentCreate,
    ProcedureConsentCreatedResponse,
    ProcedureConsentDetail,
    ProcedureConsentListItem,
    ProcedureConsentUpdate,
)

logger = logging.getLogger(__name__)


def _decode_label(raw: str) -> str:
    return unquote((raw or "").strip())


class ProcedureConsentController(Controller):
    path = "/api/procedure-consent-documents"

    @get("/")
    async def list_documents(
        self,
        state: State,
        include_tattoo: bool = Parameter(default=True, query="include_tattoo"),
    ) -> list[ProcedureConsentListItem]:
        try:
            return await state.service.list_procedure_consent_documents(
                include_tattoo=include_tattoo
            )
        except Exception as e:
            logger.exception("list_procedure_consent_documents")
            raise HTTPException(detail=str(e), status_code=500) from e

    @get("/{label:str}")
    async def get_document(self, label: str, state: State) -> ProcedureConsentDetail:
        try:
            row = await state.service.get_procedure_consent_document_detail(_decode_label(label))
            if row is None:
                raise HTTPException(detail="Tipo de piercing no encontrado.", status_code=404)
            return row
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("get_procedure_consent_document")
            raise HTTPException(detail=str(e), status_code=500) from e

    @post("/", status_code=status_codes.HTTP_201_CREATED)
    async def create_document(
        self, data: ProcedureConsentCreate, state: State
    ) -> ProcedureConsentCreatedResponse:
        try:
            label = await state.service.create_procedure_consent_document(data)
            return ProcedureConsentCreatedResponse(
                message="Tipo de piercing creado correctamente.",
                survey_option_label=label,
            )
        except ValueError as e:
            raise HTTPException(detail=str(e), status_code=400) from e
        except Exception as e:
            logger.exception("create_procedure_consent_document")
            raise HTTPException(detail=str(e), status_code=500) from e

    @put("/{label:str}")
    async def update_document(
        self, label: str, data: ProcedureConsentUpdate, state: State
    ) -> MessageResponse:
        try:
            await state.service.update_procedure_consent_document(_decode_label(label), data)
            return MessageResponse(status="success", message="Tipo de piercing actualizado.")
        except ValueError as e:
            msg = str(e)
            if msg == "NOT_FOUND":
                raise HTTPException(detail="Tipo de piercing no encontrado.", status_code=404) from e
            raise HTTPException(detail=msg, status_code=400) from e
        except Exception as e:
            logger.exception("update_procedure_consent_document")
            raise HTTPException(detail=str(e), status_code=500) from e

    @delete("/{label:str}", status_code=status_codes.HTTP_200_OK)
    async def delete_document(self, label: str, state: State) -> MessageResponse:
        try:
            await state.service.delete_procedure_consent_document(_decode_label(label))
            return MessageResponse(status="success", message="Tipo de piercing eliminado.")
        except ValueError as e:
            msg = str(e)
            if msg == "NOT_FOUND":
                raise HTTPException(detail="Tipo de piercing no encontrado.", status_code=404) from e
            raise HTTPException(detail=msg, status_code=400) from e
        except Exception as e:
            logger.exception("delete_procedure_consent_document")
            raise HTTPException(detail=str(e), status_code=500) from e
