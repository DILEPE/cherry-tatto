"""Cliente HTTP para la API Litestar."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

import requests

DEFAULT_BASE = "http://127.0.0.1:5000"


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


def get_appointments() -> Tuple[bool, int, Any]:
    return _request("GET", "/api/appointments")


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


def post_appointment_payment(appointment_id: int, amount: float, note: Optional[str] = None) -> Tuple[bool, int, Any]:
    return _request(
        "POST",
        f"/api/appointments/{appointment_id}/payments",
        json_body={"amount": float(amount), "note": note},
    )


def post_contract(payload: Dict[str, Any]) -> Tuple[bool, int, Any]:
    return _request("POST", "/api/contracts", json_body=payload)


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


def post_survey(payload: Dict[str, Any]) -> Tuple[bool, int, Any]:
    return _request("POST", "/api/surveys", json_body=payload)


def get_surveys() -> Tuple[bool, int, Any]:
    return _request("GET", "/api/surveys/")


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
