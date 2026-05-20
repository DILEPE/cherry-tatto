"""Cálculos de montos y etiquetas financieras de citas — sin Streamlit."""

from __future__ import annotations

from typing import Any


def coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def appointment_financial_totals(row: dict[str, Any]) -> tuple[float, float, float]:
    """
    Normaliza montos para UI y resumen:
    - total nunca menor que abonado (fallback datos legacy)
    - pendiente: si viene `pending_balance` de la API/MySQL es la fuente de verdad
      (ej. tras anular con saldo ya puesto en 0 y crédito en otra columna);
      si no, pendiente = max(total − abonado − saldo a favor, 0) para no ignorar créditos.
    """
    abonado = max(coerce_float(row.get("deposit"), 0.0), 0.0)
    total_raw = max(coerce_float(row.get("total_amount"), 0.0), 0.0)
    total = max(total_raw, abonado)
    cred = max(coerce_float(row.get("customer_credit"), 0.0), 0.0)
    raw_pb = row.get("pending_balance")
    if raw_pb is not None and raw_pb != "":
        pendiente = max(round(coerce_float(raw_pb, 0.0), 2), 0.0)
    else:
        pendiente = max(round(total - abonado - cred, 2), 0.0)
    return total, abonado, pendiente


def customer_credit_from_row(row: dict[str, Any]) -> float:
    """Saldo a favor del cliente asociado a esta cita (p. ej. traslado de abono al anular)."""
    return max(coerce_float(row.get("customer_credit"), 0.0), 0.0)


def calendar_month_compact_label(total: float) -> str:
    """
    Total en celda del calendario mensual: solo dígitos (sin símbolo $ ni sufijo tipo «k»).
    Por debajo de mil se muestra el valor tal cual (unidades hasta 999).
    A partir de 1.000 se trunca quitando los tres últimos dígitos.
    """
    v = int(round(max(float(total or 0), 0)))
    if v <= 0:
        return "—"
    if v < 1000:
        return str(v)
    n = v // 1000
    if n < 1000:
        return str(n)
    return f"{n:,.0f}".replace(",", ".")


def format_cop(value: float | int) -> str:
    """Formato texto COP colombiano (punto como miles)."""
    amount = int(round(float(value or 0)))
    return f"COP ${amount:,.0f}".replace(",", ".")


__all__ = [
    "appointment_financial_totals",
    "calendar_month_compact_label",
    "coerce_float",
    "customer_credit_from_row",
    "format_cop",
]
