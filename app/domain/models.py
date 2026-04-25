from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, Optional

# ==========================================
# ESQUEMAS DE ENTRADA (REQUESTS)
# ==========================================

@dataclass
class AppointmentCreate:
    """Esquema para la creación de una nueva cita."""
    name: str
    phone: str
    service: str
    date: str
    detail: Optional[str] = None
    deposit: float = 0.0
    customer_id: Optional[int] = None
    customer: Optional[Dict[str, Any]] = None  # cuerpo validado con Pydantic en el servicio

@dataclass
class ContractSign:
    """Esquema para el procesamiento de la firma de un contrato."""
    appointment_id: int
    is_minor: bool
    health_data: Dict[str, Any]
    signature: str
    tutor_signature: Optional[str] = None
    template_id: Optional[int] = None  # Para vincular con una plantilla específica 

@dataclass
class ContractTemplate:
    """Modelo para las versiones de contratos."""
    id: Optional[int]
    name: str          # Ej: "Consentimiento Tatuaje V1"
    content: str       # El texto largo del contrato
    version: str       # Ej: "1.0.2"
    is_active: bool = True

@dataclass
class Survey:
    """Modelo para la encuesta de satisfacción."""
    appointment_id: int
    rating: int  # Valor del 1 al 5
    comments: Optional[str] = None
    would_recommend: bool = True

# ==========================================
# ESQUEMAS DE SALIDA (RESPONSES)
# ==========================================

@dataclass
class APIResponse:
    """Estructura base para respuestas exitosas simples."""
    status: str
    message: str
    id: Optional[int] = None
    
@dataclass
class AppointmentResponse:
    """Respuesta tras crear una cita exitosamente."""
    id: int
    status: str
    message: str

@dataclass
class ErrorResponse:
    """Estructura para documentar errores de la API."""
    detail: str
    status_code: int