"""Fusión cliente API ↔ formulario panel al agendar cita nueva."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Optional

from app.schemas.customer import CUSTOMER_BIRTH_PENDING, CustomerCreate


def booking_customer_create_for_existing_client(
    snap: Dict[str, Any],
    *,
    first_name: str,
    last_name: str,
    phone_number: str,
    email_s: str,
    document_number: str,
) -> CustomerCreate:
    """Fusiona la ficha API (`snap`) con nombre/teléfono/correo editados en el formulario de agendamiento."""
    bd_raw = snap.get("birth_date")
    if isinstance(bd_raw, str) and bd_raw.strip():
        birth_date = date.fromisoformat(bd_raw.strip()[:10])
    elif isinstance(bd_raw, date):
        birth_date = bd_raw
    elif isinstance(bd_raw, datetime):
        birth_date = bd_raw.date()
    else:
        birth_date = CUSTOMER_BIRTH_PENDING

    doc_issue_d: Optional[date] = None
    doc_issue = snap.get("document_issue_date")
    if doc_issue is not None and str(doc_issue).strip():
        if isinstance(doc_issue, str):
            doc_issue_d = date.fromisoformat(str(doc_issue).strip()[:10])
        elif isinstance(doc_issue, date):
            doc_issue_d = doc_issue
        elif isinstance(doc_issue, datetime):
            doc_issue_d = doc_issue.date()

    raw_ty = str(snap.get("document_type") or "CC").strip().upper()
    if raw_ty not in ("CC", "TI", "CE", "PAS"):
        raw_ty = "CC"

    g_issue: Optional[date] = None
    g_raw = snap.get("guardian_document_issue_date")
    if g_raw is not None and str(g_raw).strip():
        if isinstance(g_raw, str):
            g_issue = date.fromisoformat(str(g_raw).strip()[:10])
        elif isinstance(g_raw, date):
            g_issue = g_raw
        elif isinstance(g_raw, datetime):
            g_issue = g_raw.date()

    gdt_clean: Optional[str] = None
    gdt = snap.get("guardian_document_type")
    if gdt is not None and str(gdt).strip():
        u = str(gdt).strip().upper()
        if u in ("CC", "TI", "CE", "PAS"):
            gdt_clean = u

    sm_raw = snap.get("social_media")
    social_media: Optional[str] = None
    if isinstance(sm_raw, str) and sm_raw.strip():
        social_media = sm_raw.strip()
    elif sm_raw is not None and not isinstance(sm_raw, str):
        social_media = str(sm_raw).strip() or None

    return CustomerCreate(
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        birth_date=birth_date,
        document_type=raw_ty,  # type: ignore[arg-type]
        document_number=document_number.strip(),
        document_issue_date=doc_issue_d,
        email=email_s,
        phone_number=phone_number.strip(),
        address=(str(snap["address"]).strip() if snap.get("address") else None),
        nationality=(str(snap["nationality"]).strip() if snap.get("nationality") else None),
        profession=(str(snap["profession"]).strip() if snap.get("profession") else None),
        social_media=social_media,
        emergency_contact_name=(
            str(snap["emergency_contact_name"]).strip() if snap.get("emergency_contact_name") else None
        ),
        emergency_contact_phone=(
            str(snap["emergency_contact_phone"]).strip() if snap.get("emergency_contact_phone") else None
        ),
        is_minor=bool(snap.get("is_minor")),
        guardian_name=(str(snap["guardian_name"]).strip() if snap.get("guardian_name") else None),
        guardian_document_type=gdt_clean,  # type: ignore[arg-type]
        guardian_document_number=(
            str(snap["guardian_document_number"]).strip() if snap.get("guardian_document_number") else None
        ),
        guardian_document_issue_date=g_issue,
    )


__all__ = ["booking_customer_create_for_existing_client"]
