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


def post_contract(payload: Dict[str, Any]) -> Tuple[bool, int, Any]:
    return _request("POST", "/api/contracts", json_body=payload)


def get_customer_contracts(customer_id: int) -> Tuple[bool, int, Any]:
    return _request("GET", f"/api/contracts/customer/{customer_id}")


def get_contract(contract_id: int) -> Tuple[bool, int, Any]:
    return _request("GET", f"/api/contracts/{contract_id}")


def get_templates(only_active: bool) -> Tuple[bool, int, Any]:
    return _request("GET", "/api/templates/", params={"only_active": only_active})


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
