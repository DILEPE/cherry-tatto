"""Cliente HTTP para la API Litestar."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

import requests

DEFAULT_BASE = "http://127.0.0.1:5000"

# Sentinel para PATCH de abono: campo omitido (no se sobrescribe en API).
_PAY_PATCH_OMIT = object()


def base_url() -> str:
    return os.getenv("API_BASE_URL", DEFAULT_BASE).rstrip("/")


def _request(
    method: str,
    path: str,
    *,
    json_body: Any = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 30,
) -> Tuple[bool, int, Any]:
    url = f"{base_url()}{path}"
    try:
        r = requests.request(method, url, json=json_body, params=params, timeout=timeout)
    except requests.RequestException as e:
        return False, 0, {"detail": str(e)}

    try:
        data = r.json() if r.content else None
    except ValueError:
        data = r.text
    ok = 200 <= r.status_code < 300
    return ok, r.status_code, data


def search_appointments(
    *,
    field: str,
    q: str,
    limit: int = 10,
    offset: int = 0,
    assigned_panel_user_id: Optional[int] = None,
) -> Tuple[bool, int, Any]:
    params: Dict[str, Any] = {
        "field": field,
        "q": q,
        "limit": int(limit),
        "offset": int(offset),
    }
    if assigned_panel_user_id is not None:
        params["assigned_panel_user_id"] = int(assigned_panel_user_id)
    return _request("GET", "/api/appointments/search", params=params)


def get_appointments(assigned_panel_user_id: Optional[int] = None) -> Tuple[bool, int, Any]:
    params: Optional[Dict[str, Any]] = None
    if assigned_panel_user_id is not None:
        params = {"assigned_panel_user_id": int(assigned_panel_user_id)}
    return _request("GET", "/api/appointments", params=params)


def get_appointment(appointment_id: int) -> Tuple[bool, int, Any]:
    """Detalle de una cita (mismo formato que cada elemento del listado)."""
    return _request("GET", f"/api/appointments/{int(appointment_id)}")


def get_appointments_work_performed_labels(
    appointment_ids: list[int],
) -> Tuple[bool, int, Any]:
    """Mapa id cita → tipo de perforación (encuesta), para reporte financiero."""
    ids = sorted({int(x) for x in appointment_ids if int(x) > 0})
    if not ids:
        return True, 200, {}
    return _request(
        "GET",
        "/api/appointments/work-performed-labels",
        params={"ids": ",".join(str(i) for i in ids)},
    )


def post_appointment(payload: Dict[str, Any]) -> Tuple[bool, int, Any]:
    return _request("POST", "/api/appointments", json_body=payload)


def patch_appointment_status(
    appointment_id: int,
    status: str,
    on_cancel_abono: Optional[str] = None,
) -> Tuple[bool, int, Any]:
    body: Dict[str, Any] = {"status": status}
    if status == "Cancelada" and on_cancel_abono is not None:
        body["on_cancel_abono"] = on_cancel_abono
    return _request("PATCH", f"/api/appointments/{appointment_id}/status", json_body=body)


def patch_appointment_reschedule(
    appointment_id: int,
    date_value: str,
    detail: Optional[str] = None,
) -> Tuple[bool, int, Any]:
    return _request(
        "PATCH",
        f"/api/appointments/{appointment_id}/reschedule",
        json_body={"date": date_value, "detail": detail},
    )


def patch_appointment_meta(
    appointment_id: int,
    *,
    assigned_panel_user_id: Optional[int],
    is_priority: bool,
    detail: Optional[str],
) -> Tuple[bool, int, Any]:
    body: Dict[str, Any] = {"is_priority": bool(is_priority)}
    if assigned_panel_user_id is not None:
        body["assigned_panel_user_id"] = int(assigned_panel_user_id)
    if detail is not None:
        body["detail"] = detail
    return _request(
        "PATCH",
        f"/api/appointments/{int(appointment_id)}/meta",
        json_body=body,
    )


def patch_appointment_financials(
    appointment_id: int,
    total_amount: float,
    deposit: float,
    pending_balance: float,
) -> Tuple[bool, int, Any]:
    return _request(
        "PATCH",
        f"/api/appointments/{appointment_id}/financials",
        json_body={
            "total_amount": float(total_amount),
            "deposit": float(deposit),
            "pending_balance": float(pending_balance),
        },
    )


def get_appointment_payments(appointment_id: int) -> Tuple[bool, int, Any]:
    return _request("GET", f"/api/appointments/{appointment_id}/payments")


def post_appointment_payment(
    appointment_id: int,
    amount: float,
    note: Optional[str] = None,
    paid_on: Optional[str] = None,
) -> Tuple[bool, int, Any]:
    body: Dict[str, Any] = {"amount": float(amount)}
    if note is not None:
        body["note"] = note
    if paid_on is not None:
        body["paid_on"] = paid_on
    return _request(
        "POST",
        f"/api/appointments/{appointment_id}/payments",
        json_body=body,
    )


def patch_appointment_payment(
    appointment_id: int,
    payment_id: int,
    *,
    amount: Optional[float] = None,
    note: Any = _PAY_PATCH_OMIT,
    paid_on: Any = _PAY_PATCH_OMIT,
) -> Tuple[bool, int, Any]:
    payload: Dict[str, Any] = {}
    if amount is not None:
        payload["amount"] = float(amount)
    if note is not _PAY_PATCH_OMIT:
        payload["note"] = note
    if paid_on is not _PAY_PATCH_OMIT:
        payload["paid_on"] = paid_on
    return _request(
        "PATCH",
        f"/api/appointments/{int(appointment_id)}/payments/{int(payment_id)}",
        json_body=payload,
    )


def get_appointment_receipts(appointment_id: int) -> Tuple[bool, int, Any]:
    return _request("GET", f"/api/appointments/{appointment_id}/receipts")


def fetch_appointment_receipt_pdf(appointment_id: int, receipt_id: int) -> Tuple[bool, int, bytes, str]:
    """Descarga binario PDF. El cuarto valor es nombre sugerido o mensaje de error corto."""
    url = f"{base_url()}/api/appointments/{appointment_id}/receipts/{int(receipt_id)}/pdf"
    try:
        r = requests.get(url, timeout=60)
    except requests.RequestException as e:
        return False, 0, b"", str(e)
    if not (200 <= r.status_code < 300):
        return False, r.status_code, b"", ""
    fname = f"recibo_{appointment_id}_{receipt_id}.pdf"
    cd = r.headers.get("Content-Disposition") or ""
    if "filename=" in cd:
        part = cd.split("filename=", 1)[-1].strip().strip('"')
        if part:
            fname = part.split(";", 1)[0].strip('"')
    return True, r.status_code, r.content, fname


def post_resend_appointment_receipt(appointment_id: int, receipt_id: int) -> Tuple[bool, int, Any]:
    return _request(
        "POST",
        f"/api/appointments/{int(appointment_id)}/receipts/{int(receipt_id)}/resend",
    )


def post_contract(payload: Dict[str, Any]) -> Tuple[bool, int, Any]:
    return _request("POST", "/api/contracts", json_body=payload)


def get_contract_latest_summary_for_appointment(appointment_id: int) -> Tuple[bool, int, Any]:
    return _request("GET", f"/api/contracts/appointment/{int(appointment_id)}/latest-summary")


def post_contract_complete_artist_signature(payload: Dict[str, Any]) -> Tuple[bool, int, Any]:
    return _request("POST", "/api/contracts/complete-artist-signature", json_body=payload)


def get_customer_contracts(customer_id: int) -> Tuple[bool, int, Any]:
    return _request("GET", f"/api/contracts/customer/{customer_id}")


def get_contract(contract_id: int) -> Tuple[bool, int, Any]:
    return _request("GET", f"/api/contracts/{contract_id}")


def get_templates(only_active: bool, contract_kind: Optional[str] = None) -> Tuple[bool, int, Any]:
    params: Dict[str, Any] = {"only_active": only_active}
    if contract_kind:
        params["contract_kind"] = contract_kind
    return _request("GET", "/api/templates/", params=params)


def get_template(template_id: int) -> Tuple[bool, int, Any]:
    return _request("GET", f"/api/templates/{template_id}")


def post_template(payload: Dict[str, Any]) -> Tuple[bool, int, Any]:
    return _request("POST", "/api/templates/", json_body=payload)


def put_template(template_id: int, payload: Dict[str, Any]) -> Tuple[bool, int, Any]:
    return _request("PUT", f"/api/templates/{template_id}", json_body=payload)


def delete_template(template_id: int) -> Tuple[bool, int, Any]:
    return _request("DELETE", f"/api/templates/{template_id}")


def post_panel_user_register(
    username: str,
    password: str,
    *,
    first_name: str = "",
    last_name: str = "",
    address: Optional[str] = None,
    phone: Optional[str] = None,
    store_id: int = 1,
    role: str = "vendedor",
) -> Tuple[bool, int, Any]:
    body: Dict[str, Any] = {
        "username": username,
        "password": password,
        "first_name": first_name,
        "last_name": last_name,
        "store_id": int(store_id),
        "role": role,
    }
    if address is not None:
        body["address"] = address
    if phone is not None:
        body["phone"] = phone
    return _request("POST", "/api/panel-users/register", json_body=body)


def post_panel_user_login(username: str, password: str) -> Tuple[bool, int, Any]:
    if not (username or "").strip() or not password:
        return False, 422, {"detail": "Usuario y contraseña son obligatorios."}
    return _request(
        "POST",
        "/api/panel-users/login",
        json_body={"username": username.strip().lower(), "password": password},
    )


def get_panel_users_assignable_for_appointments() -> Tuple[bool, int, Any]:
    return _request("GET", "/api/panel-users/assignable-for-appointments")


def get_panel_users() -> Tuple[bool, int, Any]:
    return _request("GET", "/api/panel-users/")


def get_panel_user(user_id: int) -> Tuple[bool, int, Any]:
    return _request("GET", f"/api/panel-users/{user_id}")


def post_panel_user_create(payload: Dict[str, Any]) -> Tuple[bool, int, Any]:
    return _request("POST", "/api/panel-users/", json_body=payload)


def patch_panel_user(user_id: int, payload: Dict[str, Any]) -> Tuple[bool, int, Any]:
    return _request("PATCH", f"/api/panel-users/{user_id}", json_body=payload)


def get_panel_user_effective_modules(user_id: int) -> Tuple[bool, int, Any]:
    return _request("GET", f"/api/panel-users/{user_id}/modules/effective")


def get_panel_user_module_grants(user_id: int) -> Tuple[bool, int, Any]:
    return _request("GET", f"/api/panel-users/{user_id}/modules")


def put_panel_user_modules(user_id: int, modules: List[str]) -> Tuple[bool, int, Any]:
    return _request("PUT", f"/api/panel-users/{user_id}/modules", json_body={"modules": modules})


def post_survey(payload: Dict[str, Any]) -> Tuple[bool, int, Any]:
    return _request("POST", "/api/surveys", json_body=payload)


def get_surveys() -> Tuple[bool, int, Any]:
    return _request("GET", "/api/surveys/")


def get_survey_for_appointment(appointment_id: int) -> Tuple[bool, int, Any]:
    """Consulta si existe encuesta para la cita (evita listar todas las encuestas)."""
    return _request("GET", f"/api/surveys/by-appointment/{int(appointment_id)}")


def get_survey_questions(
    *, include_inactive: bool = False, contract_kind: str | None = None
) -> Tuple[bool, int, Any]:
    params: Dict[str, Any] = {"include_inactive": include_inactive}
    if contract_kind is not None and str(contract_kind).strip():
        params["contract_kind"] = str(contract_kind).strip()
    return _request(
        "GET",
        "/api/survey-questions/",
        params=params,
    )


def get_survey_question_stats_summary() -> Tuple[bool, int, Any]:
    return _request("GET", "/api/survey-questions/stats/summary")


def get_survey_question_deletion_impact(question_id: int) -> Tuple[bool, int, Any]:
    return _request("GET", f"/api/survey-questions/{question_id}/deletion-impact")


def post_survey_question(payload: Dict[str, Any]) -> Tuple[bool, int, Any]:
    return _request("POST", "/api/survey-questions/", json_body=payload)


def put_survey_question(question_id: int, payload: Dict[str, Any]) -> Tuple[bool, int, Any]:
    return _request("PUT", f"/api/survey-questions/{question_id}", json_body=payload)


def delete_survey_question(question_id: int) -> Tuple[bool, int, Any]:
    return _request("DELETE", f"/api/survey-questions/{question_id}")


# --- Customers ---


def get_customers(
    *,
    limit: int = 20,
    offset: int = 0,
    search: Optional[str] = None,
    document_number: Optional[str] = None,
) -> Tuple[bool, int, Any]:
    params: Dict[str, Any] = {"limit": limit, "offset": offset}
    if search:
        params["search"] = search
    if document_number:
        params["document_number"] = document_number
    return _request("GET", "/api/customers", params=params)


def get_customer(customer_id: int) -> Tuple[bool, int, Any]:
    return _request("GET", f"/api/customers/{customer_id}")


def post_customer(payload: Dict[str, Any]) -> Tuple[bool, int, Any]:
    return _request("POST", "/api/customers", json_body=payload)


def put_customer(customer_id: int, payload: Dict[str, Any]) -> Tuple[bool, int, Any]:
    return _request("PUT", f"/api/customers/{customer_id}", json_body=payload)


def delete_customer(customer_id: int) -> Tuple[bool, int, Any]:
    return _request("DELETE", f"/api/customers/{customer_id}")


# --- Tiendas ---


def get_stores(*, include_inactive: bool = False) -> Tuple[bool, int, Any]:
    params: Dict[str, Any] = {}
    if include_inactive:
        params["include_inactive"] = True
    return _request("GET", "/api/stores", params=params or None)


def get_store(store_id: int) -> Tuple[bool, int, Any]:
    return _request("GET", f"/api/stores/{int(store_id)}")


def post_store(payload: Dict[str, Any]) -> Tuple[bool, int, Any]:
    return _request("POST", "/api/stores", json_body=payload)


def put_store(store_id: int, payload: Dict[str, Any]) -> Tuple[bool, int, Any]:
    return _request("PUT", f"/api/stores/{int(store_id)}", json_body=payload)


def delete_store(store_id: int) -> Tuple[bool, int, Any]:
    return _request("DELETE", f"/api/stores/{int(store_id)}")


def get_health_n8n() -> Tuple[bool, int, Any]:
    """GET /health/n8n en la API Litestar (sondeo real de la misma configuración que el backend)."""
    return _request("GET", "/health/n8n", timeout=25)


def check_n8n_webhook_connection() -> Tuple[str, str]:
    """
    Usa GET /health/n8n de la API (`API_BASE_URL` / .env).

    Retorna (nivel, mensaje) para Streamlit: success / warn / error.
    """
    _, code, raw = get_health_n8n()
    if isinstance(raw, dict):
        lvl = raw.get("level")
        msg = raw.get("message")
        if isinstance(lvl, str) and lvl in ("success", "warn", "error") and isinstance(msg, str):
            return lvl, msg
    if code == 0:
        det = raw.get("detail", raw) if isinstance(raw, dict) else raw
        return (
            "error",
            f"No hay conexión con la API en {base_url()} ({det}). Arranca Litestar (`uvicorn app.main:app`).",
        )
    return "error", f"Respuesta inesperada de /health/n8n (HTTP {code}): {raw!s}"
