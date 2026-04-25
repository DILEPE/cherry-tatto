"""HTTP routes for customer management (Litestar + Pydantic)."""
from __future__ import annotations

import logging
from typing import Optional

from litestar import Controller, delete, get, post, put, status_codes
from litestar.datastructures import State
from litestar.exceptions import HTTPException
from litestar.params import Parameter

from app.schemas.customer import (
    CustomerCreate,
    CustomerListResponse,
    CustomerPublic,
    CustomerUpdate,
)

logger = logging.getLogger(__name__)


class CustomerController(Controller):
    path = "/api/customers"

    @post(status_code=status_codes.HTTP_201_CREATED)
    async def create_customer(self, data: CustomerCreate, state: State) -> dict:
        try:
            cid = await state.service.create_customer(data)
            return {"id": cid, "status": "success", "message": "Customer created"}
        except ValueError as e:
            raise HTTPException(detail=str(e), status_code=400) from e
        except Exception as e:
            logger.exception("create_customer")
            raise HTTPException(detail=str(e), status_code=500) from e

    @get()
    async def list_customers(
        self,
        state: State,
        limit: int = Parameter(default=20, ge=1, le=100, query="limit"),
        offset: int = Parameter(default=0, ge=0, query="offset"),
        search: Optional[str] = Parameter(default=None, query="search"),
        document_number: Optional[str] = Parameter(default=None, query="document_number"),
    ) -> CustomerListResponse:
        try:
            return await state.service.list_customers(
                limit=limit, offset=offset, search=search, document_number=document_number
            )
        except Exception as e:
            logger.exception("list_customers")
            raise HTTPException(detail=str(e), status_code=500) from e

    @get("/{customer_id:int}")
    async def get_customer(self, customer_id: int, state: State) -> CustomerPublic:
        try:
            row = await state.service.get_customer(customer_id)
            if not row:
                raise HTTPException(detail="Customer not found", status_code=404)
            return CustomerPublic.model_validate(row)
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("get_customer")
            raise HTTPException(detail=str(e), status_code=500) from e

    @put("/{customer_id:int}")
    async def update_customer(self, customer_id: int, data: CustomerUpdate, state: State) -> dict:
        try:
            await state.service.update_customer(customer_id, data)
            return {"status": "success", "message": "Customer updated"}
        except ValueError as e:
            raise HTTPException(detail=str(e), status_code=404) from e
        except Exception as e:
            logger.exception("update_customer")
            raise HTTPException(detail=str(e), status_code=400) from e

    @delete("/{customer_id:int}", status_code=status_codes.HTTP_200_OK)
    async def delete_customer(self, customer_id: int, state: State) -> dict:
        try:
            await state.service.soft_delete_customer(customer_id)
            return {"status": "success", "message": "Customer deleted"}
        except ValueError as e:
            raise HTTPException(detail=str(e), status_code=404) from e
        except Exception as e:
            logger.exception("delete_customer")
            raise HTTPException(detail=str(e), status_code=500) from e
