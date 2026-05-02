"""Reglas de negocio para permitir la firma del contrato vinculada a una cita."""
from __future__ import annotations


def appointment_must_be_fully_paid_for_contract(
    *,
    total_amount: float | int | None,
    deposit: float | int | None,
    pending_balance: float | int | None,
) -> tuple[bool, str | None]:
    """
    Si la cita tiene valor total de trabajo (> 0), exige abono completo (sin saldo pendiente).
    Si el total es 0 o no está definido, no bloquea por montos (compatibilidad con datos sin cotizar).
    """
    total = float(total_amount or 0)
    deposit_f = float(deposit or 0)
    pending_f = float(pending_balance or 0)
    if total <= 0.01:
        return True, None
    due = round(total - deposit_f, 2)
    if round(pending_f, 2) > 0.01 or due > 0.01:
        return False, (
            "No se puede firmar el contrato mientras exista saldo pendiente. "
            "El valor total del trabajo debe estar abonado por completo en la cita (Gestión de citas → Montos)."
        )
    return True, None
