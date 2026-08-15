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


def appointment_payments_must_be_verified_for_contract(
    payments: list[dict[str, object]] | None,
) -> tuple[bool, str | None]:
    """
    Verificación de abonos por un administrador.

    No se exige al firmar el contrato ni al completar la firma del profesional
    (es una tarea posterior). Se mantiene por si se reutiliza en ese flujo.
    """
    rows = payments or []
    if not rows:
        return False, (
            "No hay abonos registrados. Registra y verifica los abonos antes de firmar el contrato."
        )
    unverified = [
        r
        for r in rows
        if not bool(int(r.get("is_verified") or 0))  # type: ignore[arg-type]
    ]
    if unverified:
        return False, (
            "Hay abonos **sin verificar**. Un **administrador** debe confirmar cada abono "
            "en la ficha de la cita antes de firmar el contrato."
        )
    return True, None
