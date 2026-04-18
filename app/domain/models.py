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

@dataclass
class ContractSign:
    """Esquema para el procesamiento de la firma de un contrato."""
    appointment_id: int
    is_minor: bool
    health_data: Dict[str, Any]
    signature: str
    tutor_signature: Optional[str] = None

# ==========================================
# ESQUEMAS DE SALIDA (RESPONSES)
# ==========================================

@dataclass
class APIResponse:
    """Estructura base para respuestas exitosas simples."""
    status: str
    message: str

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