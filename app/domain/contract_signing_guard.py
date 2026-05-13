"""Reglas de negocio para permitir la firma del contrato vinculada a una cita."""
from __future__ import annotations


def appointment_must_be_fully_paid_for_contract(
    *,
    total_amount: float | int | None,
    deposit: float | int | None,
    pending_balance: float | int | None,
) -> tuple[bool, str | None]:
    """
    Condiciones para firmar contrato vinculado a una cita (misma regla en panel y API):

    - Debe existir **valor total del trabajo** > 0 (definido en la cita).
    - El **abono** debe cubrir ese total: sin saldo pendiente (`pending_balance` y coherencia con total − abono).
    """
    total = float(total_amount or 0)
    deposit_f = float(deposit or 0)
    pending_f = float(pending_balance or 0)

    if total <= 0.01:
        return False, (
            "No se puede firmar el contrato sin un **valor total del trabajo** definido y mayor a cero. "
            "Regístralo en **Gestión de citas → Montos** antes de firmar."
        )

    due = round(total - deposit_f, 2)
    if round(pending_f, 2) > 0.01 or due > 0.01:
        return False, (
            "No se puede firmar el contrato mientras exista **saldo pendiente**. "
            "El **valor total del trabajo** debe estar **abonado por completo** en la cita "
            "(**Gestión de citas → Montos**)."
        )
    return True, None
