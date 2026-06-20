"""Esquemas Pydantic: citas."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.models import AppointmentCreate
from app.schemas.customer import CUSTOMER_EMBEDDED_IN_APPOINTMENT_DESCRIPTION, CustomerCreate

_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DESIGN_LABEL = "Descripción del diseño"
_OBSERVATIONS_LABEL = "Observaciones"
_DESIGN_SECTION_RE = re.compile(
    rf"(?:^|\n){re.escape(_DESIGN_LABEL)}:\s*(.*?)(?=\n{re.escape(_OBSERVATIONS_LABEL)}:|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_OBSERVATIONS_SECTION_RE = re.compile(
    rf"(?:^|\n){re.escape(_OBSERVATIONS_LABEL)}:\s*(.*)\Z",
    re.IGNORECASE | re.DOTALL,
)


def split_appointment_detail(detail: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Extrae descripción y observaciones desde el campo legacy `detail`."""
    raw = (detail or "").strip()
    if not raw:
        return None, None

    design_match = _DESIGN_SECTION_RE.search(raw)
    observations_match = _OBSERVATIONS_SECTION_RE.search(raw)
    if design_match or observations_match:
        design = design_match.group(1).strip() if design_match else ""
        observations = observations_match.group(1).strip() if observations_match else ""
        return design or None, observations or None

    return raw, None


def compose_appointment_detail(
    detail: Optional[str] = None,
    design_description: Optional[str] = None,
    observations: Optional[str] = None,
) -> Optional[str]:
    """Combina campos nuevos en `detail` sin romper clientes legacy."""
    design = (design_description or "").strip()
    obs = (observations or "").strip()
    legacy = (detail or "").strip()

    if not design and not obs:
        return legacy or None

    parts: list[str] = []
    if design:
        parts.append(f"{_DESIGN_LABEL}: {design}")
    elif legacy:
        parts.append(f"{_DESIGN_LABEL}: {legacy}")
    if obs:
        parts.append(f"{_OBSERVATIONS_LABEL}: {obs}")
    return "\n".join(parts) or None


def normalize_appointment_datetime_string(v: str) -> str:
    """
    Normaliza a 'YYYY-MM-DD HH:MM:00' para MySQL DATETIME.
    Acepta YYYY-MM-DD (legacy → 09:00), YYYY-MM-DD HH:MM, YYYY-MM-DD HH:MM:SS o ISO con T.
    """
    raw = (v or "").strip().replace("T", " ")
    if not raw:
        raise ValueError("La fecha/hora de la cita no puede estar vacía.")
    if _DATE_ONLY.match(raw) and len(raw) == 10:
        datetime.strptime(raw, "%Y-%m-%d")
        return f"{raw} 09:00:00"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%Y-%m-%d %H:%M:00")
        except ValueError:
            continue
    raise ValueError("Usa AAAA-MM-DD o AAAA-MM-DD HH:MM (hora local de la cita).")


class AppointmentCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=200)
    phone: str = Field(..., min_length=5, max_length=40)
    service: str = Field(..., min_length=1, max_length=120)
    date: str = Field(
        ...,
        description="YYYY-MM-DD o YYYY-MM-DD HH:MM (se guarda como DATETIME).",
    )
    detail: Optional[str] = Field(None, max_length=5000)
    design_description: Optional[str] = Field(
        default=None,
        max_length=5000,
        validation_alias=AliasChoices(
            "design_description",
            "designDescription",
            "descripcion_diseno",
            "description",
        ),
    )
    observations: Optional[str] = Field(
        default=None,
        max_length=5000,
        validation_alias=AliasChoices("observations", "observaciones", "notes"),
    )
    deposit: float = Field(ge=0, default=0)
    total_amount: float = Field(ge=0, default=0)
    pending_balance: float = Field(ge=0, default=0)
    is_priority: bool = Field(default=False, description="Cita prioritaria (etiqueta roja en agenda).")
    assigned_panel_user_id: int = Field(
        ...,
        ge=1,
        description="Usuario del panel (tatuador o perforador) al que se asigna la franja horaria.",
    )
    customer_id: Optional[int] = Field(default=None, ge=1)
    customer: Optional[CustomerCreate] = Field(
        default=None,
        description=CUSTOMER_EMBEDDED_IN_APPOINTMENT_DESCRIPTION,
    )

    @field_validator("date")
    @classmethod
    def date_ok(cls, v: str) -> str:
        return normalize_appointment_datetime_string(v)


def appointment_request_to_domain(req: AppointmentCreateRequest) -> AppointmentCreate:
    """Convierte el cuerpo validado de la API al dataclass de persistencia."""
    return AppointmentCreate(
        name=req.name,
        phone=req.phone,
        service=req.service,
        date=req.date,
        detail=compose_appointment_detail(req.detail, req.design_description, req.observations),
        deposit=req.deposit,
        total_amount=req.total_amount,
        pending_balance=req.pending_balance,
        is_priority=bool(req.is_priority),
        customer_id=req.customer_id,
        customer=req.customer.model_dump(mode="json") if req.customer is not None else None,
        assigned_panel_user_id=int(req.assigned_panel_user_id),
    )


class AppointmentListItem(BaseModel):
    """Fila típica de `SELECT * FROM appointments` (campos opcionales por versiones de esquema)."""
    model_config = ConfigDict(extra="ignore")

    id: int
    customer_name: Optional[str] = None
    phone: Optional[str] = None
    service_type: Optional[str] = None
    detail: Optional[str] = None
    design_description: Optional[str] = None
    observations: Optional[str] = None
    appointment_date: Optional[date | datetime | str] = None
    deposit: Optional[float] = None
    total_amount: Optional[float] = None
    pending_balance: Optional[float] = None
    customer_credit: Optional[float] = None
    status: Optional[str] = None
    is_priority: Optional[bool] = None
    customer_id: Optional[int] = None
    created_at: Optional[datetime | str] = None
    has_signed_contract: bool = Field(default=False, description="True si existe fila en contracts para esta cita.")
    contract_pending_artist_signature: bool = Field(
        default=False,
        description="True si hay contrato pero falta una firma válida del profesional (tatuador/perforador).",
    )
    assigned_panel_user_id: Optional[int] = None
    assigned_username: Optional[str] = None
    assigned_first_name: Optional[str] = None
    assigned_last_name: Optional[str] = None
    assigned_role: Optional[str] = None
    assigned_store_id: Optional[int] = None

    @model_validator(mode="after")
    def fill_split_detail_fields(self):
        design, observations = split_appointment_detail(self.detail)
        if self.design_description is None:
            object.__setattr__(self, "design_description", design)
        if self.observations is None:
            object.__setattr__(self, "observations", observations)
        return self


class AppointmentStatusUpdateRequest(BaseModel):
    """Si `status` es Cancelada, `on_cancel_abono` decide qué hacer con el abono de la fila."""

    model_config = ConfigDict(str_strip_whitespace=True)

    status: str = Field(..., min_length=1, max_length=30)
    on_cancel_abono: Optional[Literal["credito_cliente", "devolucion"]] = Field(
        default=None,
        description="Cancelada: registrar abono como crédito interno para el cliente, o darlo por devuelto (sin crédito).",
    )

    @field_validator("status")
    @classmethod
    def status_ok(cls, v: str) -> str:
        valid = {"Agendada", "Reprogramada", "Cancelada", "Finalizada"}
        if v not in valid:
            raise ValueError("status inválido")
        return v

    @model_validator(mode="after")
    def default_cancel_abono(self):
        """Compatibilidad: si no llega modo y se cancela, se usa crédito al cliente como antes."""
        if self.status == "Cancelada" and self.on_cancel_abono is None:
            object.__setattr__(self, "on_cancel_abono", "credito_cliente")
        return self


class AppointmentRescheduleRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, populate_by_name=True)

    date: str = Field(..., description="YYYY-MM-DD o YYYY-MM-DD HH:MM")
    detail: Optional[str] = Field(None, max_length=5000)
    design_description: Optional[str] = Field(
        default=None,
        max_length=5000,
        validation_alias=AliasChoices(
            "design_description",
            "designDescription",
            "descripcion_diseno",
            "description",
        ),
    )
    observations: Optional[str] = Field(
        default=None,
        max_length=5000,
        validation_alias=AliasChoices("observations", "observaciones", "notes"),
    )

    @field_validator("date")
    @classmethod
    def date_ok(cls, v: str) -> str:
        return normalize_appointment_datetime_string(v)


class AppointmentMetaPatchRequest(BaseModel):
    """Actualiza profesional asignado, prioridad y/o texto de detalle (sin fecha/hora)."""

    model_config = ConfigDict(str_strip_whitespace=True, populate_by_name=True)

    assigned_panel_user_id: Optional[int] = Field(default=None, ge=1)
    is_priority: bool = False
    detail: Optional[str] = Field(default=None, max_length=5000)
    design_description: Optional[str] = Field(
        default=None,
        max_length=5000,
        validation_alias=AliasChoices(
            "design_description",
            "designDescription",
            "descripcion_diseno",
            "description",
        ),
    )
    observations: Optional[str] = Field(
        default=None,
        max_length=5000,
        validation_alias=AliasChoices("observations", "observaciones", "notes"),
    )


class AppointmentFinancialUpdateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    total_amount: float = Field(ge=0)
    deposit: float = Field(ge=0)
    pending_balance: float = Field(ge=0)

    @field_validator("pending_balance")
    @classmethod
    def pending_must_match(cls, v: float, info) -> float:
        total = float(info.data.get("total_amount", 0))
        deposit = float(info.data.get("deposit", 0))
        expected = round(total - deposit, 2)
        if round(v, 2) != expected:
            raise ValueError("pending_balance debe ser total_amount - deposit")
        if expected < 0:
            raise ValueError("pending_balance no puede ser negativo")
        return v


class AppointmentPaymentCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    amount: float = Field(gt=0)
    note: Optional[str] = Field(default=None, max_length=300)
    paid_on: Optional[date] = Field(
        default=None,
        description="Día efectivo del abono (no antes de la fecha actual, según reglas del panel).",
    )

    @field_validator("paid_on")
    @classmethod
    def paid_on_allowed(cls, v: Optional[date]) -> Optional[date]:
        if v is None:
            return None
        if v < date.today():
            raise ValueError("La fecha del abono no puede ser anterior a la fecha actual.")
        return v


class AppointmentPaymentPatchRequest(BaseModel):
    """Actualización parcial de un abono registrado."""

    model_config = ConfigDict(str_strip_whitespace=True)

    amount: Optional[float] = Field(default=None, gt=0)
    note: Optional[str] = Field(default=None, max_length=300)
    paid_on: Optional[date] = None

    @field_validator("paid_on")
    @classmethod
    def paid_on_allowed(cls, v: Optional[date]) -> Optional[date]:
        if v is None:
            return None
        if v < date.today():
            raise ValueError("La fecha del abono no puede ser anterior a la fecha actual.")
        return v

    @model_validator(mode="after")
    def at_least_one(self):
        if self.amount is None and self.note is None and self.paid_on is None:
            raise ValueError("Debes enviar al menos un campo a modificar.")
        return self


class AppointmentPaymentItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    appointment_id: int
    amount: float
    note: Optional[str] = None
    paid_on: Optional[date] = None
    created_at: Optional[datetime | str] = None


class AppointmentSearchHit(BaseModel):
    """Resultado de búsqueda global de citas (fila lista + etiqueta de recibo)."""

    model_config = ConfigDict(extra="ignore")

    id: int
    customer_name: Optional[str] = None
    appointment_date: Optional[date | datetime | str] = None
    receipt_label: Optional[str] = None
    assigned_username: Optional[str] = None
    assigned_first_name: Optional[str] = None
    assigned_last_name: Optional[str] = None
    assigned_role: Optional[str] = None
    assigned_panel_user_id: Optional[int] = None
    assigned_store_id: Optional[int] = None
    service_type: Optional[str] = None
    status: Optional[str] = None
    has_signed_contract: bool = False
    contract_pending_artist_signature: bool = False


class AppointmentSearchResponse(BaseModel):
    items: list[AppointmentSearchHit]
    total: int
    limit: int
    offset: int


class AppointmentPaymentReceiptListItem(BaseModel):
    """Metadatos de un recibo PDF (sin el binario)."""

    model_config = ConfigDict(extra="ignore")

    id: int
    appointment_id: int
    customer_id: Optional[int] = None
    appointment_payment_id: Optional[int] = None
    kind: str
    amount: float
    total_amount_snapshot: float
    deposit_after: float
    pending_after: float
    note: Optional[str] = None
    file_name: str
    created_at: Optional[datetime | str] = None
