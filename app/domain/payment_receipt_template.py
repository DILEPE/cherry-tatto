"""Plantilla HTML activa `contract_kind=recibo` integrada en el PDF de orden de trabajo.

El formato Rock City (cabecera, datos del cliente, precios, franja ATENCIÓN) se mantiene.
El HTML de la plantilla activa de recibo sustituye el texto legal fijo bajo esa franja
(no se agrega un segundo documento/PDF).
"""
from __future__ import annotations

import html
import logging
from datetime import datetime
from typing import Mapping, Optional

from app.domain.payment_receipt_pdf import (
    PaymentReceiptPdfContext,
    _clean_detail_for_design,
    _fmt_cop,
    build_payment_receipt_pdf,
)

logger = logging.getLogger(__name__)


def _esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _split_appointment_when(when: str) -> tuple[str, str]:
    raw = (when or "").strip()
    if not raw:
        return "", ""
    for sep in (" ", "T"):
        if sep in raw:
            left, right = raw.split(sep, 1)
            return left.strip(), right.strip()[:5]
    return raw, ""


def receipt_placeholder_map(ctx: PaymentReceiptPdfContext) -> dict[str, str]:
    """Mapa `{{clave}}` → texto escapado para HTML."""
    issued = ctx.issued_at if isinstance(ctx.issued_at, datetime) else datetime.now()
    fecha_cita, hora_cita = _split_appointment_when(ctx.appointment_when)
    diseno = _clean_detail_for_design(ctx.detail or "")
    hist = list(ctx.payment_history or [])
    abonos_items = "".join(
        f"<li>{_esc(_fmt_cop(amt))}"
        + (f" — {_esc(note)}" if note else "")
        + "</li>"
        for amt, note in hist
    )
    abonos_html = f"<ul>{abonos_items}</ul>" if abonos_items else "<p>—</p>"

    def abono_n(i: int) -> str:
        if i < len(hist):
            return _esc(_fmt_cop(hist[i][0]))
        return ""

    money = {
        "precio": _fmt_cop(ctx.total_amount),
        "total": _fmt_cop(ctx.total_amount),
        "abono": _fmt_cop(ctx.this_payment),
        "este_abono": _fmt_cop(ctx.this_payment),
        "total_abonado": _fmt_cop(ctx.deposit_total_after),
        "depositos": _fmt_cop(ctx.deposit_total_after),
        "pendiente": _fmt_cop(ctx.pending_after),
        "saldo": _fmt_cop(ctx.pending_after),
    }
    plain = {
        "nombres": ctx.client_name or "",
        "nombre": ctx.client_name or "",
        "telefono": ctx.client_phone or "",
        "celular": ctx.client_phone or "",
        "email": ctx.client_email or "",
        "correo": ctx.client_email or "",
        "cita": ctx.appointment_when or "",
        "fecha_cita": fecha_cita,
        "hora": hora_cita,
        "hora_cita": hora_cita,
        "servicio": ctx.service or "",
        "diseno": diseno,
        "detalle": diseno,
        "tipo_recibo": ctx.kind_label or "",
        "nota": ctx.payment_note or "",
        "cita_id": str(ctx.appointment_id or ""),
        "fecha_emision": issued.strftime("%d/%m/%Y %H:%M"),
    }
    out: dict[str, str] = {f"{{{{{k}}}}}": _esc(v) for k, v in plain.items()}
    for k, v in money.items():
        out[f"{{{{{k}}}}}"] = _esc(v)
    out["{{abono_1}}"] = abono_n(0)
    out["{{abono_2}}"] = abono_n(1)
    out["{{abono_3}}"] = abono_n(2)
    out["{{abonos}}"] = abonos_html
    return out


def fill_receipt_template_html(template_content: str, ctx: PaymentReceiptPdfContext) -> str:
    """Sustituye placeholders; no envuelve en documento HTML completo."""
    body = template_content or ""
    for key, value in receipt_placeholder_map(ctx).items():
        body = body.replace(key, value)
    return body


def build_payment_receipt_pdf_with_contract(
    ctx: PaymentReceiptPdfContext,
    template_content: Optional[str] = None,
) -> bytes:
    """Orden de trabajo; si hay plantilla recibo, su texto va en la zona legal del mismo PDF."""
    content = (template_content or "").strip()
    if content:
        try:
            ctx.contract_html = fill_receipt_template_html(content, ctx)
        except Exception:
            logger.exception(
                "No se pudo preparar plantilla de recibo (cita id=%s); términos por defecto.",
                getattr(ctx, "appointment_id", 0),
            )
            ctx.contract_html = None
    else:
        ctx.contract_html = None
    return build_payment_receipt_pdf(ctx)


# Compat con imports antiguos
def render_receipt_template_html(template_content: str, ctx: PaymentReceiptPdfContext) -> str:
    return fill_receipt_template_html(template_content, ctx)


def build_payment_receipt_pdf_from_template(
    template_content: str, ctx: PaymentReceiptPdfContext
) -> bytes:
    return build_payment_receipt_pdf_with_contract(ctx, template_content)


def active_recibo_template_content(templates: list[Mapping[str, object]]) -> Optional[str]:
    """Primera plantilla activa de tipo recibo (lista ya filtrada o completa)."""
    for row in templates:
        kind = str(row.get("contract_kind") or "").strip().lower()
        active = bool(row.get("is_active"))
        if kind == "recibo" and active:
            content = row.get("content")
            if content is not None and str(content).strip():
                return str(content)
    return None
