"""Fila de reporte financiero (rango de fechas)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class FinancialReportRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    customer_name: Optional[str] = None
    phone: Optional[str] = None
    service_type: Optional[str] = None
    appointment_date: Optional[date | str] = None
    deposit: Optional[float] = None
    status: Optional[str] = None
    created_at: Optional[datetime | str] = None
