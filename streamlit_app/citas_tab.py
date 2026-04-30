"""Streamlit: Citas con calendario, franjas horarias y formulario mínimo."""
from __future__ import annotations

import calendar
import html as html_mod
from datetime import date, datetime, time
from io import BytesIO
from typing import Any, Dict, List, Optional

import streamlit as st

from pydantic import ValidationError

from app.domain.service_types import resolve_service_type
from app.schemas.customer import CustomerCreate
from streamlit_app import api_client
from streamlit_app.customer_sync import fetch_customer_by_document
from streamlit_app.validation import validate_appointment


def _api_error(payload: Any) -> str:
    if isinstance(payload, dict):
        return str(payload.get("detail", payload))
    return str(payload)


def _show_validation_errors(errors: List[Any]) -> None:
    for e in errors:
        st.markdown(
            f'<div class="m-error"><strong>{e.field}</strong>: {e.message}</div>',
            unsafe_allow_html=True,
        )


def _format_cop(value: float | int) -> str:
    amount = int(round(float(value or 0)))
    return f"COP ${amount:,.0f}".replace(",", ".")


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _financial_row_values(row: dict[str, Any]) -> tuple[float, float, float]:
    """
    Normaliza montos para UI y resumen:
    - total nunca menor que abonado (fallback datos legacy)
    - pendiente: si viene `pending_balance` de la API/MySQL es la fuente de verdad
      (ej. tras anular con saldo ya puesto en 0 y crédito en otra columna);
      si no, pendiente = max(total − abonado − saldo a favor, 0) para no ignorar créditos.
    """
    abonado = max(_to_float(row.get("deposit"), 0.0), 0.0)
    total_raw = max(_to_float(row.get("total_amount"), 0.0), 0.0)
    total = max(total_raw, abonado)
    cred = max(_to_float(row.get("customer_credit"), 0.0), 0.0)
    raw_pb = row.get("pending_balance")
    if raw_pb is not None and raw_pb != "":
        pendiente = max(round(_to_float(raw_pb, 0.0), 2), 0.0)
    else:
        pendiente = max(round(total - abonado - cred, 2), 0.0)
    return total, abonado, pendiente


def _customer_credit_value(row: dict[str, Any]) -> float:
    """Saldo a favor del cliente asociado a esta cita (p. ej. traslado de abono al anular)."""
    return max(_to_float(row.get("customer_credit"), 0.0), 0.0)


def _xlsx_border_thin() -> Any:
    from openpyxl.styles import Border, Side

    s = Side(style="thin", color="FF9CA3AF")
    return Border(left=s, right=s, top=s, bottom=s)


def _excel_set_cell(ws: Any, row: int, col: int, value: Any, *, font=None, alignment=None, border=None, fill=None) -> None:
    """Asignación de celda compatible con coordenadas 1-based tipo Excel."""
    cell = ws.cell(row=row, column=col, value=value)
    if font is not None:
        cell.font = font
    if alignment is not None:
        cell.alignment = alignment
    if border is not None:
        cell.border = border
    if fill is not None:
        cell.fill = fill


def _excel_apply_border_block(ws: Any, row_min: int, row_max: int, col_min: int, col_max: int, border: Any) -> None:
    for r in range(row_min, row_max + 1):
        for c in range(col_min, col_max + 1):
            ws.cell(row=r, column=c).border = border


def _citas_filtered_to_excel_bytes(rows: list[dict[str, Any]], *, generated_at: Optional[datetime] = None) -> bytes:
    """Genera .xlsx financiero estilizado: título, encabezados en negrita y tablas demarcadas."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    gen_dt = generated_at or datetime.now()
    fecha_etiqueta = gen_dt.strftime("%d/%m/%Y %H:%M")

    datos: list[list[Any]] = []
    for r in rows:
        tot, abo, pend = _financial_row_values(r)
        cred = _customer_credit_value(r)
        nombre = str(r.get("customer_name") or r.get("name") or "").strip()
        datos.append(
            [
                nombre,
                round(tot, 2),
                round(abo, 2),
                round(pend, 2),
                round(cred, 2),
            ]
        )

    headers = ["Cliente", "Valor total (COP)", "Abonado (COP)", "Pendiente (COP)", "Saldo a favor (COP)"]
    ncol = len(headers)

    wb = Workbook()
    bd = _xlsx_border_thin()
    font_title = Font(bold=True, size=14, color="FF111827")
    font_sub = Font(size=10, color="FF4B5563")
    font_header = Font(bold=True, size=11, color="FF111827")
    font_body = Font(size=10, color="FF374151")
    fill_header = PatternFill(fill_type="solid", fgColor="FFE5E7EB")
    align_center = Alignment(horizontal="center", vertical="center", wrap_text=False)
    align_left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    align_right_num = Alignment(horizontal="right", vertical="center")

    # --- Hoja detalle ---
    ws1 = wb.active
    ws1.title = "Datos financieros"
    ws1.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncol)
    ws1.cell(1, 1, "Informe financiero — Citas Cherry Ink · Rock City")
    ws1.cell(1, 1).font = font_title
    ws1.cell(1, 1).alignment = align_center

    ws1.merge_cells(start_row=2, start_column=1, end_row=2, end_column=ncol)
    ws1.cell(2, 1, f"Generado: {fecha_etiqueta}")
    ws1.cell(2, 1).font = font_sub
    ws1.cell(2, 1).alignment = align_center

    header_row = 4
    for col in range(1, ncol + 1):
        _excel_set_cell(
            ws1,
            header_row,
            col,
            headers[col - 1],
            font=font_header,
            fill=fill_header,
            alignment=align_left if col == 1 else align_right_num,
            border=bd,
        )

    row_start_body = header_row + 1
    if datos:
        for i, row_vals in enumerate(datos):
            r = row_start_body + i
            for col in range(1, ncol + 1):
                v = row_vals[col - 1]
                align = align_left if col == 1 else align_right_num
                _excel_set_cell(ws1, r, col, v, font=font_body, alignment=align, border=bd)
            rmax = r
        _excel_apply_border_block(ws1, header_row, rmax, 1, ncol, bd)
    else:
        ws1.merge_cells(start_row=row_start_body, start_column=1, end_row=row_start_body, end_column=ncol)
        c_msg = ws1.cell(row=row_start_body, column=1, value="Sin filas para los filtros actuales.")
        c_msg.font = font_body
        c_msg.alignment = align_left
        _excel_apply_border_block(ws1, header_row, row_start_body, 1, ncol, bd)

    for col in range(1, ncol + 1):
        letter = get_column_letter(col)
        ws1.column_dimensions[letter].width = 36 if col == 1 else 18

    # --- Resumen ---
    ws2 = wb.create_sheet("Resumen financiero", 1)
    rtot = rabo = rpend = rfav = 0.0
    for rr in rows:
        t, a, p = _financial_row_values(rr)
        rtot += t
        rabo += a
        rpend += p
        rfav += _customer_credit_value(rr)

    ws2.merge_cells(start_row=1, start_column=1, end_row=1, end_column=2)
    ws2.cell(1, 1, "Resumen financiero — mismos filtros que el panel")
    ws2.cell(1, 1).font = font_title
    ws2.cell(1, 1).alignment = align_center
    ws2.merge_cells(start_row=2, start_column=1, end_row=2, end_column=2)
    ws2.cell(2, 1, f"Generado: {fecha_etiqueta}")
    ws2.cell(2, 1).font = font_sub
    ws2.cell(2, 1).alignment = align_center

    resumen_labels = ["Total valor trabajo (COP)", "Total abonado (COP)", "Total pendiente (COP)", "Total saldo a favor (COP)", "Cantidad de citas"]
    resumen_vals: list[Any] = [
        round(rtot, 2),
        round(rabo, 2),
        round(rpend, 2),
        round(rfav, 2),
        len(rows) if rows else 0,
    ]
    hdr_r = 4
    _excel_set_cell(ws2, hdr_r, 1, "Concepto", font=font_header, fill=fill_header, alignment=align_left, border=bd)
    _excel_set_cell(ws2, hdr_r, 2, "Valor", font=font_header, fill=fill_header, alignment=align_right_num, border=bd)
    for i, lab in enumerate(resumen_labels):
        r = hdr_r + 1 + i
        _excel_set_cell(ws2, r, 1, lab, font=font_body, alignment=align_left, border=bd)
        _excel_set_cell(ws2, r, 2, resumen_vals[i], font=font_body, alignment=align_right_num, border=bd)
    _excel_apply_border_block(ws2, hdr_r, hdr_r + len(resumen_labels), 1, 2, bd)
    ws2.column_dimensions["A"].width = 44
    ws2.column_dimensions["B"].width = 22

    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio.getvalue()


def _parse_date(val: Any) -> date:
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str) and val:
        s = val.strip().replace("T", " ")
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    return date(1990, 1, 1)


def _format_appt_when(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, datetime):
        return val.strftime("%d/%m/%Y %H:%M")
    if isinstance(val, date):
        return val.strftime("%d/%m/%Y")
    s = str(val).strip().replace("T", " ")
    if not s:
        return ""
    for c in (s, s[:19], s[:10]):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(c, fmt)
                if fmt == "%Y-%m-%d":
                    return dt.strftime("%d/%m/%Y")
                return dt.strftime("%d/%m/%Y %H:%M")
            except ValueError:
                pass
    return s[:16]


def _time_slot_options() -> List[str]:
    """Franjas cada 30 min entre 08:00 y 20:00 inclusive."""
    slots: List[str] = []
    minutes = 8 * 60
    last = 20 * 60
    while minutes <= last:
        h, mm = divmod(minutes, 60)
        slots.append(f"{h:02d}:{mm:02d}")
        minutes += 30
    return slots


_BOOKING_WORK_KIND_ORDER = ("piercing", "tatuaje", "limpieza_tatuaje", "cambio_piercing")
_BOOKING_WORK_KIND_META: Dict[str, Dict[str, Any]] = {
    "piercing": {
        "label": "Piercing (colocación)",
        "duration_slots": 2,
        "service_token": "piercing",
        "detail_tag": "[Piercing]",
    },
    "tatuaje": {
        "label": "Tatuaje (sesión)",
        "duration_slots": 4,
        "service_token": "tattoo",
        "detail_tag": "[Tatuaje]",
    },
    "limpieza_tatuaje": {
        "label": "Limpieza de tatuaje",
        "duration_slots": 1,
        "service_token": "tattoo",
        "detail_tag": "[Limpieza tatuaje]",
    },
    "cambio_piercing": {
        "label": "Cambio de piercing",
        "duration_slots": 1,
        "service_token": "piercing",
        "detail_tag": "[Cambio piercing]",
    },
}


def _booking_client_age_years(bd: date) -> int:
    t = date.today()
    return t.year - bd.year - ((t.month, t.day) < (bd.month, bd.day))


def _booking_is_minor_birth(bd: date) -> bool:
    return _booking_client_age_years(bd) < 18


def _duration_slots_for_existing_appointment(row: dict[str, Any]) -> int:
    """Franjas de 30 min ocupadas por citas ya guardadas (heurística por servicio y detalle)."""
    svc = str(row.get("service_type") or row.get("service") or "").strip().lower()
    det = str(row.get("detail") or "").strip().lower()
    combined = f"{svc} {det}"
    if "limpieza" in det:
        return 1
    if "cambio" in det and "pierc" in combined:
        return 1
    if "tatu" in combined or "tattoo" in svc:
        return 4
    if "pierc" in combined or svc == "piercing":
        return 2
    if "other" in svc or "otro" in svc:
        return 1
    return 2


def _appointments_same_day_raw(items: list[dict[str, Any]], day: date) -> list[dict[str, Any]]:
    """Citas de ese día usando la lista completa de API (sin filtrar por nombre), para no solapar huecos."""
    out: list[dict[str, Any]] = []
    for row in items:
        try:
            d = _parse_date(row.get("appointment_date", row.get("date")))
        except (TypeError, ValueError):
            continue
        if d != day:
            continue
        out.append(row)
    return out


def _busy_slot_indices_for_day(day_rows: list[dict[str, Any]], slot_list: list[str]) -> set[int]:
    busy: set[int] = set()
    n = len(slot_list)
    for row in day_rows:
        if str(row.get("status") or "").strip().lower() == "cancelada":
            continue
        hm = _appt_time_hm(row.get("appointment_date", row.get("date")))
        if hm == "—":
            continue
        try:
            start_idx = slot_list.index(hm)
        except ValueError:
            continue
        dur = _duration_slots_for_existing_appointment(row)
        for j in range(start_idx, min(start_idx + dur, n)):
            busy.add(j)
    return busy


def _available_start_slots(slot_list: list[str], need_slots: int, busy: set[int]) -> list[str]:
    n = len(slot_list)
    out: list[str] = []
    for i in range(n):
        if i + need_slots > n:
            break
        if any(j in busy for j in range(i, i + need_slots)):
            continue
        out.append(slot_list[i])
    return out


def _service_and_detail_for_work_kind(kind: str, user_detail: str) -> tuple[str, Optional[str]]:
    meta = _BOOKING_WORK_KIND_META.get(kind) or _BOOKING_WORK_KIND_META["piercing"]
    svc = resolve_service_type(meta["service_token"])
    tag = meta["detail_tag"]
    extra = (user_detail or "").strip()
    if extra:
        return svc, f"{tag} {extra}".strip()
    return svc, tag


def _combine_appointment_datetime(d: date, slot_hm: str) -> str:
    slot_hm = (slot_hm or "09:00").strip()
    parts = slot_hm.split(":")
    h = int(parts[0])
    m = int(parts[1]) if len(parts) > 1 else 0
    return f"{d.strftime('%Y-%m-%d')} {h:02d}:{m:02d}:00"


def _parse_existing_slot(val: Any) -> tuple[date, str]:
    d = _parse_date(val)
    s = str(val or "").strip().replace("T", " ")
    opts = _time_slot_options()
    if len(s) >= 16:
        chunk = s[11:16]
        if chunk in opts:
            return d, chunk
    return d, "09:00" if "09:00" in opts else opts[0]


def _appt_time_hm(val: Any) -> str:
    """Hora HH:MM para listados compactos; '—' si solo hay fecha."""
    if val is None:
        return "—"
    if isinstance(val, datetime):
        return val.strftime("%H:%M")
    if isinstance(val, date) and not isinstance(val, datetime):
        return "—"
    s = str(val).strip().replace("T", " ")
    if not s:
        return "—"
    for chunk, fmt in ((s[:19], "%Y-%m-%d %H:%M:%S"), (s[:16], "%Y-%m-%d %H:%M")):
        try:
            return datetime.strptime(chunk, fmt).strftime("%H:%M")
        except ValueError:
            pass
    return "—"


def _appointments_by_day_sorted(items: list[dict[str, Any]]) -> dict[tuple[int, int, int], list[dict[str, Any]]]:
    """Citas agrupadas por día local, ordenadas por hora de inicio."""
    buckets: dict[tuple[int, int, int], list[dict[str, Any]]] = {}

    def sort_key(r: dict[str, Any]) -> tuple[int, int]:
        raw = r.get("appointment_date", r.get("date"))
        if isinstance(raw, datetime):
            return (raw.hour, raw.minute)
        s = str(raw or "").strip().replace("T", " ")
        for chunk, fmt in ((s[:19], "%Y-%m-%d %H:%M:%S"), (s[:16], "%Y-%m-%d %H:%M")):
            try:
                dt = datetime.strptime(chunk, fmt)
                return (dt.hour, dt.minute)
            except ValueError:
                pass
        return (99, 99)

    for row in items:
        try:
            d = _parse_date(row.get("appointment_date", row.get("date")))
        except (TypeError, ValueError):
            continue
        key = (d.year, d.month, d.day)
        buckets.setdefault(key, []).append(row)
    for appts in buckets.values():
        appts.sort(key=sort_key)
    return buckets


def _normalize_phone_digits(phone: Any) -> str:
    return "".join(c for c in str(phone or "") if c.isdigit())


def _client_history_key(row: dict[str, Any]) -> str:
    """Clave estable para contar citas históricas por cliente (id, teléfono o nombre)."""
    cid = row.get("customer_id")
    if cid is not None and str(cid).strip() != "":
        try:
            return f"id:{int(cid)}"
        except (TypeError, ValueError):
            pass
    ph = _normalize_phone_digits(row.get("phone"))
    if ph:
        return f"ph:{ph}"
    nm = str(row.get("customer_name") or row.get("name") or "").strip().lower()
    if nm:
        return f"nm:{nm}"
    return f"row:{row.get('id', 0)}"


def _appointment_counts_by_client(items: list[dict[str, Any]]) -> dict[str, int]:
    """Total de citas por cliente en todo el histórico cargado (lista API)."""
    counts: dict[str, int] = {}
    for row in items:
        k = _client_history_key(row)
        counts[k] = counts.get(k, 0) + 1
    return counts


def _row_is_priority(row: dict[str, Any]) -> bool:
    v = row.get("is_priority")
    if v is True or v == 1:
        return True
    if isinstance(v, str) and v.strip().lower() in ("1", "true", "yes"):
        return True
    return False


def _client_pill_class(row: dict[str, Any], counts_by_client: dict[str, int]) -> str:
    """
    Prioridad de etiqueta: Reprogramada > Prioritaria > Cliente recurrente (>1 cita) > Cliente nuevo.
    Así, prioritaria y reprogramada prevalecen sobre el criterio de antigüedad del cliente.
    """
    stv = str(row.get("status") or "").strip().lower()
    if stv == "reprogramada":
        return "cli-pill-reprogramada"
    if _row_is_priority(row):
        return "cli-pill-priority"
    key = _client_history_key(row)
    if counts_by_client.get(key, 0) > 1:
        return "cli-pill-returning"
    return "cli-pill-new"


def _customer_name_pill_html(row: dict[str, Any], counts_by_client: dict[str, int]) -> str:
    name = str(row.get("customer_name") or row.get("name") or "").strip() or "—"
    cls = _client_pill_class(row, counts_by_client)
    return f'<span class="cli-pill {cls}">{html_mod.escape(name)}</span>'


def _calendar_overflow_row_html(row: dict[str, Any], counts_by_client: dict[str, int]) -> str:
    """Línea para el diálogo de citas extra: hora + nombre completo con pill de cliente."""
    hm = _appt_time_hm(row.get("appointment_date", row.get("date")))
    st_cl = str(row.get("status") or "").strip().lower()
    dim = "opacity:0.55;" if st_cl == "cancelada" else ""
    pill = _customer_name_pill_html(row, counts_by_client)
    return (
        f"<div style='font-size:0.86rem;line-height:1.5;{dim}margin:0.4rem 0;padding-bottom:0.35rem;"
        f"border-bottom:1px solid rgba(148,163,184,0.35);display:flex;flex-wrap:wrap;align-items:center;gap:0.35rem'>"
        f"<span style='font-weight:600'>{html_mod.escape(hm)}</span><span>·</span>{pill}</div>"
    )


def _calendar_appt_line_html(
    row: dict[str, Any],
    counts_by_client: dict[str, int],
    *,
    short_len: int = 12,
) -> str:
    """HTML de una línea en celda del calendario (hora + nombre en pill)."""
    hm = _appt_time_hm(row.get("appointment_date", row.get("date")))
    nm = str(row.get("customer_name") or row.get("name") or "").strip() or "—"
    short = nm if len(nm) <= short_len else nm[: short_len - 1] + "…"
    cls = _client_pill_class(row, counts_by_client)
    st_cl = str(row.get("status") or "").strip().lower()
    dim = "opacity:0.5;" if st_cl == "cancelada" else ""
    pill = f'<span class="cli-pill {cls}">{html_mod.escape(short)}</span>'
    inner = f"{html_mod.escape(hm)} · {pill}"
    title = html_mod.escape(f"{hm} · {nm}")
    return (
        f"<div title='{title}' style='font-size:0.72rem;line-height:1.35;{dim}white-space:nowrap;"
        f"overflow:hidden;text-overflow:ellipsis'>{inner}</div>"
    )


_MONTHS_ES = (
    "",
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
)


def _weekday_headers_es() -> List[str]:
    return ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


def _shift_years(base: date, years: int) -> date:
    target_year = base.year + years
    try:
        return base.replace(year=target_year)
    except ValueError:
        return base.replace(year=target_year, day=28)


def _date_range_100y_window() -> tuple[date, date]:
    today = date.today()
    return _shift_years(today, -100), _shift_years(today, 100)


def _init_appt_form_state_once() -> None:
    if st.session_state.get("_ap_form_ready"):
        return
    slot_opts = _time_slot_options()
    default_slot = "09:00" if "09:00" in slot_opts else slot_opts[0]
    defaults: Dict[str, Any] = {
        "ap_fn": "",
        "ap_ln": "",
        "ap_phone": "",
        "ap_email": "",
        "ap_ad": date.today(),
        "ap_slot": default_slot,
        "ap_det": "",
        "ap_dep": 0.0,
        "ap_total": 0.0,
        "ap_priority": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    if "ap_work_kind" not in st.session_state:
        st.session_state["ap_work_kind"] = "piercing"
    if "ap_birth_date" not in st.session_state:
        st.session_state["ap_birth_date"] = date(2000, 1, 1)
    if "ap_doc_type" not in st.session_state:
        st.session_state["ap_doc_type"] = "CC"
    st.session_state["_ap_form_ready"] = True


def _pop_booking_document_session() -> None:
    for k in (
        "_ap_booking_customer_id",
        "_ap_need_new_customer",
        "_ap_doc_verified",
        "_ap_verify_msg",
        "_ap_verify_level",
        "_ap_verified_doc_number",
        "ap_doc_number",
    ):
        st.session_state.pop(k, None)


def _reset_appointment_form_state() -> None:
    for key in (
        "ap_fn",
        "ap_ln",
        "ap_phone",
        "ap_email",
        "ap_ad",
        "ap_slot",
        "ap_det",
        "ap_dep",
        "ap_total",
        "ap_priority",
        "ap_work_kind",
        "ap_birth_date",
        "ap_doc_type",
    ):
        st.session_state.pop(key, None)
    st.session_state["_ap_form_ready"] = False
    _pop_booking_document_session()


@st.dialog("Agendar cita", width="large", dismissible=False)
def _dialog_agendar_cita() -> None:
    _init_appt_form_state_once()

    picked_raw = st.session_state.get("ap_ad")
    if picked_raw is None:
        st.error("Selecciona un día en el calendario para agendar.")
        if st.button("Cerrar", use_container_width=True, key="btn_appt_close_no_day"):
            st.session_state.pop("_ap_dlg", None)
            st.rerun()
        return
    picked = picked_raw if isinstance(picked_raw, date) else _parse_date(picked_raw)
    today_d = date.today()
    if picked < today_d:
        st.error("No se pueden agendar citas en fechas pasadas. Elige un día de hoy en adelante en el calendario.")
        if st.button("Cerrar", use_container_width=True, key="btn_appt_close_past_date"):
            st.session_state.pop("_ap_dlg", None)
            st.rerun()
        return

    st.markdown(
        """
        <style>
          .dlg-appt-req-banner {
            border-left: 4px solid #FF007F;
            padding: 0.5rem 0.85rem;
            margin: 0.75rem 0 0.75rem 0;
            background: rgba(255, 0, 127, 0.12);
            border-radius: 8px;
            font-size: 0.95rem;
            line-height: 1.45;
            color: #f3f4f6;
          }
          .dlg-appt-col-h {
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            color: #A79AFF;
            margin: 0 0 0.5rem 0;
          }
        </style>
        <div class="dlg-appt-req-banner">Campos obligatorios</div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<p class="dlg-appt-col-h">Tipo de trabajo</p>', unsafe_allow_html=True)
    st.radio(
        "¿Qué se va a realizar? *",
        options=list(_BOOKING_WORK_KIND_ORDER),
        key="ap_work_kind",
        format_func=lambda k: (
            f"{_BOOKING_WORK_KIND_META[k]['label']} "
            f"({_BOOKING_WORK_KIND_META[k]['duration_slots'] * 30} min)"
        ),
        help="La duración define cuántas franjas de 30 min se bloquean; la hora solo ofrece inicios libres ese día.",
    )

    st.markdown('<p class="dlg-appt-col-h">Verificación de documento</p>', unsafe_allow_html=True)
    st.text_input(
        "Número de documento *",
        key="ap_doc_number",
        placeholder="Sin puntos ni espacios, si es posible",
    )
    if st.button("Verificar documento", type="secondary", use_container_width=True, key="ap_btn_verify_doc"):
        doc_in = (st.session_state.get("ap_doc_number") or "").strip()
        if len(doc_in) < 5:
            st.session_state["_ap_verify_level"] = "error"
            st.session_state["_ap_verify_msg"] = "Ingresa un documento válido (mínimo 5 caracteres)."
            st.session_state["_ap_doc_verified"] = False
        else:
            ok_f, msg_f, row_f = fetch_customer_by_document(doc_in)
            if not ok_f:
                st.session_state["_ap_verify_level"] = "error"
                st.session_state["_ap_verify_msg"] = msg_f
                st.session_state["_ap_doc_verified"] = False
            elif msg_f == "not_found":
                st.session_state["_ap_booking_customer_id"] = None
                st.session_state["_ap_need_new_customer"] = True
                st.session_state["_ap_doc_verified"] = True
                st.session_state["_ap_verified_doc_number"] = doc_in
                st.session_state["_ap_verify_level"] = "warning"
                st.session_state["_ap_verify_msg"] = (
                    "Cliente no registrado. Indica fecha de nacimiento y tipo de documento; completa nombre, apellido, "
                    "celular y correo. El tutor u otros datos legales pueden completarse después (estado Agendada)."
                )
            else:
                st.session_state["_ap_booking_customer_id"] = int(row_f["id"])
                st.session_state["_ap_need_new_customer"] = False
                st.session_state["_ap_doc_verified"] = True
                st.session_state["_ap_verified_doc_number"] = doc_in
                st.session_state["ap_fn"] = str(row_f.get("first_name") or "")
                st.session_state["ap_ln"] = str(row_f.get("last_name") or "")
                st.session_state["ap_phone"] = str(row_f.get("phone_number") or "")
                st.session_state["ap_email"] = str(row_f.get("email") or "")
                st.session_state["_ap_verify_level"] = "success"
                st.session_state["_ap_verify_msg"] = f"Cliente encontrado (id {row_f['id']}). Datos cargados."
        st.rerun()

    v_lvl = st.session_state.get("_ap_verify_level")
    v_msg = st.session_state.get("_ap_verify_msg")
    if v_msg and v_lvl:
        if v_lvl == "error":
            st.error(v_msg)
        elif v_lvl == "success":
            st.success(v_msg)
        else:
            st.warning(v_msg)

    if st.session_state.get("_ap_need_new_customer"):
        st.caption(
            "Para **menores de edad** no se exige tutor al crear la cita; complétalo después en la ficha del cliente o antes del contrato."
        )
        b_min, b_max = _date_range_100y_window()
        st.date_input(
            "Fecha de nacimiento del cliente *",
            min_value=b_min,
            max_value=today_d,
            key="ap_birth_date",
            format="DD/MM/YYYY",
        )
        st.selectbox(
            "Tipo de documento *",
            options=["CC", "TI", "CE", "PAS"],
            format_func=lambda x: {
                "CC": "CC — Cédula",
                "TI": "TI — Tarjeta de identidad",
                "CE": "CE — Extranjería",
                "PAS": "PAS — Pasaporte",
            }[x],
            key="ap_doc_type",
        )
        _bd0 = st.session_state.get("ap_birth_date")
        if isinstance(_bd0, date) and _booking_is_minor_birth(_bd0):
            st.info(
                "Cliente **menor de edad**: se marcará automáticamente en el registro. **TI** solo aplica a menores."
            )

    st.markdown(
        f"**Fecha de la cita:** {picked.strftime('%d/%m/%Y')} _(elegida en el calendario)_"
    )

    slot_opts = _time_slot_options()
    wk = str(st.session_state.get("ap_work_kind") or "piercing")
    if wk not in _BOOKING_WORK_KIND_META:
        wk = "piercing"
    need_slots = int(_BOOKING_WORK_KIND_META[wk]["duration_slots"])
    raw_appt_list = list(st.session_state.get("_ap_list") or [])
    day_rows_cal = _appointments_same_day_raw(raw_appt_list, picked)
    busy_idx = _busy_slot_indices_for_day(day_rows_cal, slot_opts)
    avail_slots = _available_start_slots(slot_opts, need_slots, busy_idx)
    cur_slot = st.session_state.get("ap_slot")
    if avail_slots and cur_slot not in avail_slots:
        st.session_state["ap_slot"] = avail_slots[0]

    if not avail_slots:
        st.warning(
            "No quedan franjas libres ese día para esta duración. Prueba otro día o revisa las citas ya cargadas."
        )
        slot = None
    else:
        slot = st.selectbox(
            "Franja de inicio *",
            options=avail_slots,
            key="ap_slot",
            help=f"Se reservan {need_slots} franja(s) de 30 min desde esta hora.",
        )
        st.caption(f"Inicio **{slot}** hora local (duración **{need_slots * 30}** min).")

    col_left, col_right = st.columns(2)
    with col_left:
        st.markdown('<p class="dlg-appt-col-h">Cliente</p>', unsafe_allow_html=True)
        fn = st.text_input("Nombre *", key="ap_fn")
        ln = st.text_input("Apellido *", key="ap_ln")
        phone = st.text_input("Celular *", key="ap_phone")
        st.text_input("Correo electrónico *", key="ap_email")
    with col_right:
        st.markdown('<p class="dlg-appt-col-h">Cita y montos</p>', unsafe_allow_html=True)
        detail = st.text_area(
            "Notas u observaciones (opcional)",
            height=80,
            key="ap_det",
            help="Se guardan junto a la etiqueta del tipo de trabajo (piercing, limpieza, cambio).",
        )
        st.checkbox(
            "Cita prioritaria",
            key="ap_priority",
            help="Se muestra con etiqueta roja en calendario y listado (prevalece sobre cliente nuevo/recurrente salvo reprogramación).",
        )
        total_amount = st.number_input("Valor total del trabajo (COP) *", min_value=0.0, step=10000.0, key="ap_total")
        deposit = st.number_input("Saldo abonado (COP) *", min_value=0.0, step=10000.0, key="ap_dep")
        pending_balance = round(float(total_amount) - float(deposit), 2)
        st.caption(f"Saldo pendiente calculado: {_format_cop(max(pending_balance, 0))}")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Crear cita", type="primary", use_container_width=True, key="btn_appt_create"):
            if not st.session_state.get("_ap_doc_verified"):
                st.error("Debes verificar el documento antes de crear la cita.")
                return
            doc_in = (st.session_state.get("ap_doc_number") or "").strip()
            if len(doc_in) < 5:
                st.error("El número de documento no es válido.")
                return
            snap = (st.session_state.get("_ap_verified_doc_number") or "").strip()
            if snap and snap != doc_in:
                st.error("El documento cambió respecto al verificado. Pulsa de nuevo «Verificar documento».")
                return
            cust_id = st.session_state.get("_ap_booking_customer_id")
            need_new = bool(st.session_state.get("_ap_need_new_customer"))
            wk_submit = str(st.session_state.get("ap_work_kind") or "piercing")
            if wk_submit not in _BOOKING_WORK_KIND_META:
                wk_submit = "piercing"
            need_slots_submit = int(_BOOKING_WORK_KIND_META[wk_submit]["duration_slots"])
            slot_opts_chk = _time_slot_options()
            raw_chk = list(st.session_state.get("_ap_list") or [])
            day_chk = _appointments_same_day_raw(raw_chk, picked)
            busy_chk = _busy_slot_indices_for_day(day_chk, slot_opts_chk)
            avail_chk = _available_start_slots(slot_opts_chk, need_slots_submit, busy_chk)
            if not avail_chk:
                st.error("No hay franja disponible ese día para la duración de este trabajo.")
                return
            slot_str = (st.session_state.get("ap_slot") or "").strip()
            if slot_str not in avail_chk:
                st.error("La franja elegida ya no está libre. Vuelve a seleccionar la hora.")
                return
            detail_raw = str(st.session_state.get("ap_det") or "")
            service, detail_for_api = _service_and_detail_for_work_kind(wk_submit, detail_raw)
            full_name = f"{(fn or '').strip()} {(ln or '').strip()}".strip()
            dt_str = _combine_appointment_datetime(picked, slot_str)
            email_s = (st.session_state.get("ap_email") or "").strip()
            valid, errs = validate_appointment(
                full_name,
                (phone or "").strip(),
                email_s,
                service,
                dt_str,
                detail_raw,
                deposit,
            )
            if not valid:
                _show_validation_errors(errs)
                return
            if deposit > total_amount:
                st.error("El saldo abonado no puede ser mayor que el valor total del trabajo.")
                return
            if picked < today_d:
                st.error("La fecha de la cita no puede ser anterior a hoy.")
                return

            appt_payload: Dict[str, Any] = {
                "name": full_name,
                "phone": (phone or "").strip(),
                "service": (service or "").strip(),
                "date": dt_str,
                "detail": detail_for_api,
                "deposit": float(deposit),
                "total_amount": float(total_amount),
                "pending_balance": float(max(pending_balance, 0)),
                "is_priority": bool(st.session_state.get("ap_priority")),
            }
            if cust_id is not None:
                appt_payload["customer_id"] = int(cust_id)
            elif need_new:
                bd_new = st.session_state.get("ap_birth_date")
                if not isinstance(bd_new, date):
                    st.error("Indica la fecha de nacimiento del cliente.")
                    return
                doc_ty = str(st.session_state.get("ap_doc_type") or "CC")
                if doc_ty not in ("CC", "TI", "CE", "PAS"):
                    doc_ty = "CC"
                if doc_ty == "TI" and not _booking_is_minor_birth(bd_new):
                    st.error("La tarjeta de identidad (TI) solo aplica a menores de edad.")
                    return
                minor_flag = _booking_is_minor_birth(bd_new)
                try:
                    c_new = CustomerCreate(
                        first_name=(fn or "").strip(),
                        last_name=(ln or "").strip(),
                        birth_date=bd_new,
                        document_type=doc_ty,  # type: ignore[arg-type]
                        document_number=doc_in,
                        document_issue_date=None,
                        email=email_s,
                        phone_number=(phone or "").strip(),
                        address=None,
                        is_minor=minor_flag,
                        guardian_name=None,
                        guardian_document_type=None,
                        guardian_document_number=None,
                        guardian_document_issue_date=None,
                    )
                except ValidationError as ve:
                    st.error(str(ve))
                    return
                appt_payload["customer"] = c_new.model_dump(mode="json")
            else:
                st.error("Verifica el documento antes de crear la cita.")
                return

            ok_a, code_a, data_a = api_client.post_appointment(appt_payload)
            if ok_a:
                st.session_state["_ap_reload"] = True
                st.success("Cita creada correctamente.")
                _reset_appointment_form_state()
                st.session_state.pop("_ap_dlg", None)
                st.rerun()
            else:
                st.error(f"Error HTTP {code_a}: {_api_error(data_a)}")
    with c2:
        if st.button("Cancelar", use_container_width=True, key="btn_appt_cancel"):
            _reset_appointment_form_state()
            st.session_state.pop("_ap_dlg", None)
            st.rerun()


def _render_main_calendar(
    buckets: dict[tuple[int, int, int], list[dict[str, Any]]],
    counts_by_client: dict[str, int],
    *,
    max_lines: int = 4,
) -> None:
    """Vista principal: mes con citas por día; al pulsar el día se abre el diálogo de agendamiento."""
    ym_key = "_ap_cal_ym"
    today = date.today()
    if ym_key not in st.session_state:
        st.session_state[ym_key] = (today.year, today.month)
    y, m = st.session_state[ym_key]

    st.markdown("##### Calendario de citas")
    st.caption(
        "Pulsa el **número del día** (hoy o futuro) para agendar; solo eliges la **hora** y debes **verificar documento**. "
        "Si hay **hasta cuatro** citas ese día, usa **Ver citas del día** para listarlas todas y editarlas. "
        "Si hay **más de cuatro**, solo **+N citas más** abre ese listado (el botón «Ver citas…» no aparece). "
        "Etiquetas: naranja = reprogramada, roja = prioritaria, azul = recurrente, fucsia = nuevo."
    )

    n1, n2, n3 = st.columns([1, 3, 1])
    with n1:
        if st.button("◀ Mes", key="cal_main_prev_m"):
            st.session_state.pop("_cal_overflow_day", None)
            if m <= 1:
                st.session_state[ym_key] = (y - 1, 12)
            else:
                st.session_state[ym_key] = (y, m - 1)
            st.rerun()
    with n2:
        st.markdown(
            f"<div style='text-align:center;font-weight:600;font-size:1.05rem'>{_MONTHS_ES[m]} {y}</div>",
            unsafe_allow_html=True,
        )
    with n3:
        if st.button("Mes ▶", key="cal_main_next_m"):
            st.session_state.pop("_cal_overflow_day", None)
            if m >= 12:
                st.session_state[ym_key] = (y + 1, 1)
            else:
                st.session_state[ym_key] = (y, m + 1)
            st.rerun()

    hdr_cells = st.columns(7)
    for i, lab in enumerate(_weekday_headers_es()):
        hdr_cells[i].markdown(
            f"<div style='text-align:center;font-size:0.72rem;opacity:0.85;font-weight:600'>{lab}</div>",
            unsafe_allow_html=True,
        )
    for week in calendar.monthcalendar(y, m):
        row_cells = st.columns(7)
        for i, d in enumerate(week):
            with row_cells[i]:
                if d == 0:
                    st.markdown("<div class='cal-cell-spacer'></div>", unsafe_allow_html=True)
                else:
                    day_rows = buckets.get((y, m, d), [])
                    parts: list[str] = []
                    for r in day_rows[:max_lines]:
                        parts.append(_calendar_appt_line_html(r, counts_by_client, short_len=12))
                    more = len(day_rows) - max_lines
                    body = "".join(parts) if parts else "<div style='font-size:0.72rem;opacity:0.55'>—</div>"
                    st.markdown(
                        f"<div class='cal-cell'>{body}</div>",
                        unsafe_allow_html=True,
                    )
                    if more > 0:
                        if st.button(
                            f"+{more} citas más",
                            key=f"cal_ov_open_{y}_{m}_{d}",
                            use_container_width=True,
                            help="Ver todas las citas del día con etiquetas y acciones",
                        ):
                            st.session_state["_cal_overflow_day"] = (y, m, d)
                            st.rerun()
                    elif len(day_rows) > 0:
                        if st.button(
                            "Ver citas del día",
                            key=f"cal_day_list_{y}_{m}_{d}",
                            use_container_width=True,
                            help="Ver citas del día: firmar contrato, reprogramar, montos o anular",
                        ):
                            st.session_state["_cal_overflow_day"] = (y, m, d)
                            st.rerun()
                    picked_cell = date(y, m, d)
                    is_past = picked_cell < date.today()
                    if st.button(
                        str(d),
                        key=f"cal_main_day_{y}_{m}_{d}",
                        use_container_width=True,
                        disabled=is_past,
                        help="No se pueden agendar citas en fechas pasadas" if is_past else None,
                    ):
                        st.session_state.pop("_cal_overflow_day", None)
                        _pop_booking_document_session()
                        st.session_state["ap_ad"] = date(y, m, d)
                        st.session_state["_ap_dlg"] = "create"
                        st.rerun()


@st.dialog("Citas del día", width="large", dismissible=False)
def _dialog_calendar_day_appointments(
    buckets: dict[tuple[int, int, int], list[dict[str, Any]]],
    hist_counts: dict[str, int],
) -> None:
    tup = st.session_state.get("_cal_overflow_day")
    if not tup:
        return
    y, m, d = int(tup[0]), int(tup[1]), int(tup[2])
    day_rows = list(buckets.get((y, m, d), []))
    day_date = date(y, m, d)
    if not day_rows:
        st.info("No hay citas para este día con los filtros actuales.")
        if st.button("Cerrar", key="cal_dlg_close_empty", use_container_width=True):
            st.session_state.pop("_cal_overflow_day", None)
            st.rerun()
        return
    st.markdown(f"**{day_date.strftime('%d/%m/%Y')}** · **{len(day_rows)}** cita(s)")
    st.caption(
        "Mismas etiquetas de cliente que en el calendario. **Firmar contrato** abre la vista de firma; "
        "Reprogramar o Montos cierran este panel y abren el formulario correspondiente."
    )
    for idx, r in enumerate(day_rows):
        st.markdown(_calendar_overflow_row_html(r, hist_counts), unsafe_allow_html=True)
        appt_id = int(r.get("id", 0) or 0)
        status = str(r.get("status") or "Agendada")
        has_customer = r.get("customer_id") is not None
        firmar_disabled = appt_id <= 0 or not has_customer or status in {"Cancelada", "Finalizada"}
        repro_disabled = appt_id <= 0 or status == "Cancelada"
        montos_disabled = appt_id <= 0 or status not in {"Agendada", "Reprogramada"}
        anular_disabled = appt_id <= 0 or status in {"Cancelada", "Finalizada"}
        b0, b1, b2, b3 = st.columns(4)
        with b0:
            st.link_button(
                "Firmar contrato",
                url=f"?view=contract_sign&appointment_id={appt_id}",
                disabled=firmar_disabled,
                use_container_width=True,
                key=f"cal_dlg_firmar_{appt_id}_{y}_{m}_{d}_{idx}",
            )
        with b1:
            if st.button(
                "Reprogramar",
                key=f"cal_dlg_repr_{appt_id}_{y}_{m}_{d}_{idx}",
                disabled=repro_disabled,
                use_container_width=True,
                help="Cambiar fecha, hora o detalle",
            ):
                st.session_state.pop("_cal_overflow_day", None)
                st.session_state["_ap_reprogram_item"] = r
                st.rerun()
        with b2:
            if st.button(
                "Montos",
                key=f"cal_dlg_fin_{appt_id}_{y}_{m}_{d}_{idx}",
                disabled=montos_disabled,
                use_container_width=True,
                help="Valor total, pendiente y abonos",
            ):
                st.session_state.pop("_cal_overflow_day", None)
                st.session_state["_ap_fin_item"] = r
                st.rerun()
        with b3:
            if st.button(
                "Anular",
                key=f"cal_dlg_can_{appt_id}_{y}_{m}_{d}_{idx}",
                disabled=anular_disabled,
                use_container_width=True,
            ):
                st.session_state.pop("_cal_overflow_day", None)
                st.session_state["_ap_cancel_item"] = r
                st.rerun()
        if idx < len(day_rows) - 1:
            st.divider()
    if st.button("Cerrar", key="cal_dlg_close", use_container_width=True):
        st.session_state.pop("_cal_overflow_day", None)
        st.rerun()


def _fetch_appointments() -> None:
    ok, code, data = api_client.get_appointments()
    if ok and isinstance(data, list):
        st.session_state["_ap_list"] = data
        st.session_state["_ap_err"] = None
    else:
        st.session_state["_ap_list"] = []
        st.session_state["_ap_err"] = f"HTTP {code}: {_api_error(data)}"


def _status_pill_html(status: str) -> str:
    normalized = (status or "Agendada").strip().lower()
    cls = {
        "agendada": "pill-agendada",
        "reprogramada": "pill-reprogramada",
        "cancelada": "pill-cancelada",
        "finalizada": "pill-finalizada",
    }.get(normalized, "pill-default")
    return f'<span class="ap-pill {cls}">{status or "Agendada"}</span>'


def _render_cita_row_actions(r: Dict[str, Any], *, show_firma: bool = True) -> None:
    """
    Menú de acciones por fila. `show_firma=False` omite el enlace de firma (p. ej. en pestaña Reporte;
    la firma va en el diálogo «Citas del día» del calendario).
    """
    appt_id = int(r.get("id", 0) or 0)
    status = str(r.get("status") or "Agendada")
    has_customer = r.get("customer_id") is not None
    firmar_disabled = appt_id <= 0 or not has_customer or status in {"Cancelada", "Finalizada"}
    repro_disabled = appt_id <= 0 or status == "Cancelada"
    montos_disabled = appt_id <= 0 or status not in {"Agendada", "Reprogramada"}
    anular_disabled = appt_id <= 0 or status in {"Cancelada", "Finalizada"}

    pop = getattr(st, "popover", None)
    if pop:
        with pop("Acciones", use_container_width=True):
            if appt_id > 0:
                st.caption(f"Cita #{appt_id}")
            if show_firma:
                st.link_button(
                    "Firmar contrato",
                    url=f"?view=contract_sign&appointment_id={appt_id}",
                    disabled=firmar_disabled,
                    use_container_width=True,
                    key=f"pop_firmar_{appt_id}",
                )
            if st.button(
                "Reprogramar cita",
                disabled=repro_disabled,
                use_container_width=True,
                key=f"pop_repr_{appt_id}",
                help="Antes columna «Mover»: cambiar fecha/detalle manteniendo el estado hábil.",
            ):
                st.session_state["_ap_reprogram_item"] = r
                st.rerun()
            if st.button(
                "Montos",
                disabled=montos_disabled,
                use_container_width=True,
                key=f"pop_fin_{appt_id}",
            ):
                st.session_state["_ap_fin_item"] = r
                st.rerun()
            if st.button(
                "Anular",
                disabled=anular_disabled,
                use_container_width=True,
                key=f"pop_can_{appt_id}",
            ):
                st.session_state["_ap_cancel_item"] = r
                st.rerun()
        return

    if show_firma:
        ln1, ln2 = st.columns(2)
        with ln1:
            st.link_button(
                "Firmar",
                url=f"?view=contract_sign&appointment_id={appt_id}",
                disabled=firmar_disabled,
                use_container_width=True,
                key=f"fb_compact_{appt_id}",
            )
        with ln2:
            if st.button("Mover", disabled=repro_disabled, use_container_width=True, key=f"fb_repr_{appt_id}"):
                st.session_state["_ap_reprogram_item"] = r
                st.rerun()
    else:
        if st.button("Mover", disabled=repro_disabled, use_container_width=True, key=f"fb_repr_{appt_id}"):
            st.session_state["_ap_reprogram_item"] = r
            st.rerun()
    bn1, bn2 = st.columns(2)
    with bn1:
        if st.button("Montos", disabled=montos_disabled, use_container_width=True, key=f"fb_fin_{appt_id}"):
            st.session_state["_ap_fin_item"] = r
            st.rerun()
    with bn2:
        if st.button("Anular", disabled=anular_disabled, use_container_width=True, key=f"fb_can_{appt_id}"):
            st.session_state["_ap_cancel_item"] = r
            st.rerun()


def _apply_appointment_filters(
    items: list[dict[str, Any]],
    *,
    use_date_range: bool = True,
    name_key: str = "_ap_f_name",
    service_key: str = "_ap_f_service",
    status_key: str = "_ap_f_status",
) -> list[dict[str, Any]]:
    text = str(st.session_state.get(name_key) or "").strip().lower()
    svc = str(st.session_state.get(service_key) or "Todos")
    status = str(st.session_state.get(status_key) or "Todos")
    from_date = st.session_state.get("_ap_f_from") if use_date_range else None
    to_date = st.session_state.get("_ap_f_to") if use_date_range else None
    filtered: list[dict[str, Any]] = []
    for row in items:
        name_value = str(row.get("customer_name", row.get("name", "")) or "")
        service_value = str(row.get("service_type", row.get("service", "")) or "")
        status_value = str(row.get("status") or "Agendada")
        appt_date = _parse_date(row.get("appointment_date", row.get("date")))
        if text and text not in name_value.lower():
            continue
        if svc != "Todos" and service_value != svc:
            continue
        if status != "Todos" and status_value != status:
            continue
        if from_date and appt_date < from_date:
            continue
        if to_date and appt_date > to_date:
            continue
        filtered.append(row)
    return filtered


def _cleanup_reprogram_dialog_state() -> None:
    keys = ("_ap_reprogram_seed_appt_id", "ap_reprogram_date", "ap_reprogram_slot", "ap_reprogram_detail")
    for k in keys:
        st.session_state.pop(k, None)


@st.dialog("Reprogramar cita", width="medium", dismissible=False)
def _dialog_reprogramar_cita() -> None:
    appt = st.session_state.get("_ap_reprogram_item") or {}
    appt_id = int(appt.get("id", 0) or 0)
    if appt_id <= 0:
        st.error("No se encontró la cita a reprogramar.")
        if st.button("Cerrar", use_container_width=True):
            st.session_state.pop("_ap_reprogram_item", None)
            _cleanup_reprogram_dialog_state()
            st.rerun()
        return
    seed_key = "_ap_reprogram_seed_appt_id"
    detail_default = str(appt.get("detail") or "")
    _, max_date_appt = _date_range_100y_window()
    # Una sola fuente de verdad: session_state por key — evita value+key (provoca glitch del popover Calendar)
    if st.session_state.get(seed_key) != appt_id:
        st.session_state[seed_key] = appt_id
        d0, sl0 = _parse_existing_slot(appt.get("appointment_date", appt.get("date")))
        today_d = date.today()
        st.session_state["ap_reprogram_date"] = d0 if d0 >= today_d else today_d
        st.session_state["ap_reprogram_slot"] = sl0
        st.session_state["ap_reprogram_detail"] = detail_default

    st.caption(f"Cita #{appt_id} · {appt.get('customer_name', appt.get('name', ''))}")
    # Detalle primero para no autofocos en el calendar al abrir el diálogo
    new_detail = st.text_area(
        "Detalle actualizado (opcional)",
        height=90,
        key="ap_reprogram_detail",
    )
    today_d = date.today()
    new_date = st.date_input(
        "Nueva fecha de cita",
        min_value=today_d,
        max_value=max_date_appt,
        key="ap_reprogram_date",
        format="DD/MM/YYYY",
    )
    slot_opts = _time_slot_options()
    cur_sl = st.session_state.get("ap_reprogram_slot")
    if cur_sl not in slot_opts:
        st.session_state["ap_reprogram_slot"] = slot_opts[0]
    new_slot = st.selectbox("Nueva franja horaria *", options=slot_opts, key="ap_reprogram_slot")
    dt_reschedule = _combine_appointment_datetime(new_date, str(new_slot))
    c1, c2 = st.columns(2)
    with c1:
        if st.button(
            "Guardar reprogramación",
            type="primary",
            use_container_width=True,
            key="ap_reprogram_save_btn",
        ):
            ok, code, data = api_client.patch_appointment_reschedule(
                appt_id,
                dt_reschedule,
                (new_detail or "").strip() or None,
            )
            if ok:
                st.success("Cita reprogramada correctamente.")
                st.session_state["_ap_reload"] = True
                st.session_state.pop("_ap_reprogram_item", None)
                _cleanup_reprogram_dialog_state()
                st.rerun()
            else:
                st.error(f"Error HTTP {code}: {_api_error(data)}")
    with c2:
        if st.button("Cancelar", use_container_width=True, key="ap_reprogram_close_btn"):
            st.session_state.pop("_ap_reprogram_item", None)
            _cleanup_reprogram_dialog_state()
            st.rerun()


def _label_cancel_abono(v: str) -> str:
    if v == "credito_cliente":
        return "Saldo a favor del cliente — el abono pasa a crédito interno y deja de contar como cobrado sobre la cita"
    return "Devolución — el abono deja la cita como no cobrado (sin saldo a favor aquí)"

@st.dialog("Confirmar anulación", width="medium", dismissible=False)
def _dialog_cancelar_cita() -> None:
    appt = st.session_state.get("_ap_cancel_item") or {}
    appt_id = int(appt.get("id", 0) or 0)
    if appt_id <= 0:
        st.error("No se encontró la cita a anular.")
        if st.button("Cerrar", use_container_width=True, key="ap_cancel_close_missing"):
            st.session_state.pop("_ap_cancel_item", None)
            st.rerun()
        return
    deposit = float(appt.get("deposit") or 0)
    warning = (
        f"Vas a anular la cita #{appt_id} de "
        f"{appt.get('customer_name', appt.get('name', 'cliente'))}. Esta acción cambia el estado a Cancelada."
    )
    if deposit > 0:
        warning += f" Hay {_format_cop(deposit)} abonados en esta fila."
    else:
        warning += " No hay abonos registrados en esta cita."
    st.warning(warning)

    cancel_abono: str
    if deposit > 0:
        st.markdown("Si hubo abono, cómo debe reflejarse para **resumen y totales**:", unsafe_allow_html=True)
        cancel_abono = st.radio(
            "Tratamiento del abono",
            ("credito_cliente", "devolucion"),
            format_func=_label_cancel_abono,
            horizontal=False,
            key=f"dlg_cancel_abono_radio_{appt_id}",
            label_visibility="visible",
        )
    else:
        cancel_abono = "devolucion"
        st.caption("Sin abono; la anulación solo cierra la cita en el sistema.")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Sí, anular", type="primary", use_container_width=True, key="ap_cancel_confirm_btn"):
            ok, code, data = api_client.patch_appointment_status(appt_id, "Cancelada", cancel_abono)
            if ok:
                st.session_state["_ap_reload"] = True
                st.session_state.pop("_ap_cancel_item", None)
                st.rerun()
            else:
                st.error(f"Error HTTP {code}: {_api_error(data)}")
    with c2:
        if st.button("No, volver", use_container_width=True, key="ap_cancel_back_btn"):
            st.session_state.pop("_ap_cancel_item", None)
            st.rerun()


@st.dialog("Ajustar montos", width="medium", dismissible=False)
def _dialog_ajustar_montos() -> None:
    appt = st.session_state.get("_ap_fin_item") or {}
    appt_id = int(appt.get("id", 0) or 0)
    status = str(appt.get("status") or "Agendada")
    if appt_id <= 0:
        st.error("No se encontró la cita.")
        if st.button("Cerrar", use_container_width=True, key="ap_fin_close_missing"):
            st.session_state.pop("_ap_fin_item", None)
            st.rerun()
        return
    if status not in {"Agendada", "Reprogramada"}:
        st.error("Solo puedes editar montos en estados Agendada o Reprogramada.")
        if st.button("Cerrar", use_container_width=True, key="ap_fin_close_invalid"):
            st.session_state.pop("_ap_fin_item", None)
            st.rerun()
        return
    st.caption(f"Cita #{appt_id} · Estado: {status}")
    current_total = float(appt.get("total_amount") or 0)
    current_deposit = float(appt.get("deposit") or 0)
    total_amount = st.number_input(
        "Valor total del trabajo (COP)",
        min_value=0.0,
        step=10000.0,
        value=current_total,
        key="ap_fin_total",
    )
    pending = round(float(total_amount) - float(current_deposit), 2)
    st.caption(f"Abonado actual: {_format_cop(current_deposit)}")
    st.caption(f"Saldo pendiente calculado: {_format_cop(max(pending, 0))}")

    ok_p, code_p, payments = api_client.get_appointment_payments(appt_id)
    st.markdown("##### Historial de abonos")
    if ok_p and isinstance(payments, list):
        if payments:
            for p in payments:
                when = str(p.get("created_at") or "")
                note = str(p.get("note") or "Sin nota")
                amount = _to_float(p.get("amount"), 0.0)
                st.write(f"- {when[:19]} · {_format_cop(amount)} · {note}")
        else:
            st.info("Aún no hay abonos registrados.")
    else:
        st.warning(f"No se pudo cargar historial (HTTP {code_p}).")

    extra_payment = st.number_input(
        "Agregar abono adicional (COP)",
        min_value=0.0,
        step=10000.0,
        value=0.0,
        key="ap_fin_extra_payment",
    )
    payment_note = st.text_input(
        "Nota del abono (opcional)",
        value="",
        key="ap_fin_extra_note",
        placeholder="Ej: abono en efectivo",
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Guardar", type="primary", use_container_width=True, key="ap_fin_save_btn"):
            if current_deposit > total_amount:
                st.error("El abonado acumulado no puede ser mayor al valor total.")
                return
            ok, code, data = api_client.patch_appointment_financials(
                appt_id,
                float(total_amount),
                float(current_deposit),
                float(max(pending, 0)),
            )
            if not ok:
                st.error(f"Error HTTP {code}: {_api_error(data)}")
                return
            if extra_payment > 0:
                ok_pay, code_pay, data_pay = api_client.post_appointment_payment(
                    appt_id,
                    float(extra_payment),
                    (payment_note or "").strip() or None,
                )
                if not ok_pay:
                    st.error(f"No se pudo registrar abono (HTTP {code_pay}): {_api_error(data_pay)}")
                    return
            st.success("Montos y abonos actualizados.")
            st.session_state["_ap_reload"] = True
            st.session_state.pop("_ap_fin_item", None)
            st.rerun()
    with c2:
        if st.button("Cancelar", use_container_width=True, key="ap_fin_cancel_btn"):
            st.session_state.pop("_ap_fin_item", None)
            st.session_state.pop("ap_fin_total", None)
            st.session_state.pop("ap_fin_extra_payment", None)
            st.session_state.pop("ap_fin_extra_note", None)
            st.rerun()


def _inject_citas_shared_styles() -> None:
    """Estilos para calendario, pills de estado/cliente y cabeceras de tabla."""
    st.markdown(
        """
        <style>
        .ap-pill {
            display: inline-block;
            border-radius: 999px;
            padding: 0.18rem 0.62rem;
            font-size: 0.78rem;
            font-weight: 600;
            line-height: 1.1rem;
            border: 1px solid transparent;
        }
        .pill-agendada { background: #e8f1ff; color: #16406f; border-color: #bdd2f4; }
        .pill-reprogramada { background: #fff2df; color: #7a4a03; border-color: #f5d3a0; }
        .pill-cancelada { background: #fdeaea; color: #7f1f1f; border-color: #efbcbc; }
        .pill-finalizada { background: #e8f8ec; color: #1f6b31; border-color: #b8e2c2; }
        .pill-default { background: #f2f3f5; color: #374151; border-color: #d1d5db; }
        .ap-col-title {
            display: inline-block;
            font-weight: 700;
            letter-spacing: 0.02em;
            color: #111827;
            background: #f3f4f6;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 0.18rem 0.45rem;
            white-space: nowrap;
            line-height: 1.35;
        }
        .cal-cell {
            border: 1px solid rgba(148, 163, 184, 0.5);
            border-radius: 8px;
            padding: 0.3rem 0.35rem 0.15rem 0.35rem;
            min-height: 4.6rem;
            margin-bottom: 0.25rem;
            background: rgba(17, 24, 39, 0.28);
        }
        .cal-cell-spacer {
            min-height: 0.5rem;
        }
        .cli-pill {
            display: inline-block;
            border-radius: 999px;
            padding: 0.06rem 0.4rem;
            font-weight: 600;
            line-height: 1.2;
            vertical-align: middle;
            border: 1px solid transparent;
        }
        .cli-pill-reprogramada { background: #fff7ed; color: #ea580c; border-color: #fdba74; }
        .cli-pill-priority { background: #fef2f2; color: #dc2626; border-color: #f87171; }
        .cli-pill-returning { background: #eff6ff; color: #2563eb; border-color: #93c5fd; }
        .cli-pill-new { background: #fdf2f8; color: #db2777; border-color: #f9a8d4; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _init_appt_tab_session_state() -> None:
    if "_ap_page" not in st.session_state:
        st.session_state["_ap_page"] = 0
    if "_ap_limit" not in st.session_state:
        st.session_state["_ap_limit"] = 10
    if "_ap_reload" not in st.session_state:
        st.session_state["_ap_reload"] = True
    if "_ap_f_name" not in st.session_state:
        st.session_state["_ap_f_name"] = ""
    if "_ap_f_service" not in st.session_state:
        st.session_state["_ap_f_service"] = "Todos"
    if "_ap_f_status" not in st.session_state:
        st.session_state["_ap_f_status"] = "Todos"
    if "_ap_f_from" not in st.session_state:
        st.session_state["_ap_f_from"] = None
    if "_ap_f_to" not in st.session_state:
        st.session_state["_ap_f_to"] = None
    if "_ap_cal_f_name" not in st.session_state:
        st.session_state["_ap_cal_f_name"] = ""
    if "_ap_cal_f_service" not in st.session_state:
        st.session_state["_ap_cal_f_service"] = "Todos"
    if "_ap_cal_f_status" not in st.session_state:
        st.session_state["_ap_cal_f_status"] = "Todos"


def _sync_appointments_from_api() -> None:
    if st.session_state.get("_ap_reload"):
        _fetch_appointments()
        st.session_state["_ap_reload"] = False


def render_reporte_citas_tab() -> None:
    """Listado paginado, totales y export Excel (informe financiero) con los mismos filtros."""
    _init_appt_tab_session_state()
    _inject_citas_shared_styles()
    _sync_appointments_from_api()

    if st.session_state.get("_ap_err"):
        st.error(st.session_state["_ap_err"])

    items = list(st.session_state.get("_ap_list") or [])
    svc_values = sorted(
        {
            str(i.get("service_type", i.get("service", "")) or "").strip()
            for i in items
            if str(i.get("service_type", i.get("service", "")) or "").strip()
        }
    )
    status_values = ["Agendada", "Reprogramada", "Finalizada", "Cancelada"]
    st.markdown("##### Reporte financiero — citas")
    st.caption(
        "Filtra el listado y los totales; descarga el Excel con el mismo criterio. "
        "El calendario de agendamiento está en **Gestión citas**."
    )
    st.markdown("##### Filtros")
    f1, f2, f3, f4, f5 = st.columns([1.3, 1.0, 1.0, 0.9, 0.9])
    with f1:
        st.text_input("Filtrar nombre", key="_ap_f_name", placeholder="Nombre cliente")
    with f2:
        st.selectbox("Servicio", options=["Todos", *svc_values], key="_ap_f_service")
    with f3:
        st.selectbox("Estado", options=["Todos", *status_values], key="_ap_f_status")
    with f4:
        st.date_input("Desde", key="_ap_f_from")
    with f5:
        st.date_input("Hasta", key="_ap_f_to")

    hist_counts = _appointment_counts_by_client(items)
    filtered_items = _apply_appointment_filters(items)

    total_trabajo = 0.0
    total_abonado = 0.0
    total_pendiente = 0.0
    total_credito_favor = 0.0
    for row in filtered_items:
        row_total, row_abonado, row_pendiente = _financial_row_values(row)
        total_trabajo += row_total
        total_abonado += row_abonado
        total_pendiente += row_pendiente
        total_credito_favor += _customer_credit_value(row)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total trabajo", _format_cop(total_trabajo))
    m2.metric("Total abonado", _format_cop(total_abonado))
    m3.metric("Total saldo pendiente", _format_cop(total_pendiente))
    m4.metric("Saldo a favor (filtro)", _format_cop(total_credito_favor))

    _informe_dt = datetime.now()
    try:
        _xlsx_agenda = _citas_filtered_to_excel_bytes(filtered_items, generated_at=_informe_dt)
    except Exception as e:
        _xlsx_agenda = b""
        if filtered_items:
            st.warning(f"No se pudo generar el Excel. Instala `openpyxl` en el venv: {e}")
    _dl_left, _dl_right = st.columns([4, 1])
    with _dl_right:
        st.download_button(
            label="Descargar Excel",
            help="Exporta financiero del filtro actual (nombre cliente y montos; hoja resumen).",
            data=_xlsx_agenda,
            file_name=(
                "Informe-finanzas-citas-"
                f"{_informe_dt.strftime('%Y-%m-%d-%H%M')}.xlsx"
            ),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            disabled=len(filtered_items) == 0 or len(_xlsx_agenda) == 0,
            key="btn_reporte_fin_xlsx",
        )

    st.markdown("##### Listado de citas")
    total = len(filtered_items)
    limit = int(st.session_state["_ap_limit"])
    page = int(st.session_state["_ap_page"])
    total_pages = max(1, (total + limit - 1) // limit)
    if page >= total_pages:
        page = max(0, total_pages - 1)
        st.session_state["_ap_page"] = page
    start = page * limit
    rows = filtered_items[start : start + limit]

    colw = [1.48, 0.92, 0.82, 0.78, 0.78, 0.92, 0.85, 0.76, 1.52]
    h1, h2, h3, h4, h5, h6, h7, h8, h9 = st.columns(colw)
    h1.markdown('<span class="ap-col-title">Nombre</span>', unsafe_allow_html=True)
    h2.markdown('<span class="ap-col-title">Servicio</span>', unsafe_allow_html=True)
    h3.markdown('<span class="ap-col-title">Fecha y hora</span>', unsafe_allow_html=True)
    h4.markdown('<span class="ap-col-title">Total</span>', unsafe_allow_html=True)
    h5.markdown('<span class="ap-col-title">Abonado</span>', unsafe_allow_html=True)
    h6.markdown('<span class="ap-col-title">Pendiente</span>', unsafe_allow_html=True)
    h7.markdown('<span class="ap-col-title">A favor</span>', unsafe_allow_html=True)
    h8.markdown('<span class="ap-col-title">Estado</span>', unsafe_allow_html=True)
    h9.markdown('<span class="ap-col-title">Acciones</span>', unsafe_allow_html=True)
    for r in rows:
        c1, c2, c3, c4, c5, c6, c7, c8, c9 = st.columns(colw)
        c1.markdown(_customer_name_pill_html(r, hist_counts), unsafe_allow_html=True)
        c2.write(r.get("service_type", r.get("service", "")))
        c3.write(_format_appt_when(r.get("appointment_date", r.get("date", ""))))
        total_amount, deposit_amount, pending_balance = _financial_row_values(r)
        credito = _customer_credit_value(r)
        c4.write(_format_cop(total_amount))
        c5.write(_format_cop(deposit_amount))
        c6.write(_format_cop(pending_balance))
        c7.write("—" if credito <= 0 else _format_cop(credito))
        status = str(r.get("status") or "Agendada")
        c8.markdown(_status_pill_html(status), unsafe_allow_html=True)
        with c9:
            _render_cita_row_actions(r, show_firma=False)

    p1, p2, p3 = st.columns([1, 1, 2.5])
    with p1:
        st.write("")
        if st.button("◀", disabled=page <= 0, use_container_width=True, key="rep_ap_page_prev"):
            st.session_state["_ap_page"] = max(0, page - 1)
            st.rerun()
    with p2:
        st.write("")
        if st.button("▶", disabled=(page + 1) * limit >= total if total else True, use_container_width=True, key="rep_ap_page_next"):
            st.session_state["_ap_page"] = page + 1
            st.rerun()
    with p3:
        st.write("")
        st.caption(f"Página {page + 1}/{total_pages} · Total filtrado: {total} cita(s)")

    if st.session_state.get("_ap_reprogram_item"):
        _dialog_reprogramar_cita()
    if st.session_state.get("_ap_fin_item"):
        _dialog_ajustar_montos()
    if st.session_state.get("_ap_cancel_item"):
        _dialog_cancelar_cita()


def render_citas_tab() -> None:
    """Calendario, agendar y diálogo de citas del día; datos financieros y tabla en **Reporte**."""
    _init_appt_tab_session_state()
    _inject_citas_shared_styles()
    _sync_appointments_from_api()

    if st.session_state.get("_ap_err"):
        st.error(st.session_state["_ap_err"])

    items = list(st.session_state.get("_ap_list") or [])
    svc_values = sorted(
        {
            str(i.get("service_type", i.get("service", "")) or "").strip()
            for i in items
            if str(i.get("service_type", i.get("service", "")) or "").strip()
        }
    )
    status_values = ["Agendada", "Reprogramada", "Finalizada", "Cancelada"]

    st.markdown("##### Gestión citas — calendario")
    st.caption(
        "Agenda y consulta rápida por día. Mismos criterios que en **Reporte** (nombre, servicio, estado), "
        "sin rango de fechas; la tabla, totales y Excel siguen en **Reporte**."
    )

    st.markdown("##### Filtros del calendario")
    cf1, cf2, cf3 = st.columns([1.3, 1.0, 1.0])
    with cf1:
        st.text_input("Filtrar nombre", key="_ap_cal_f_name", placeholder="Nombre cliente")
    with cf2:
        st.selectbox("Servicio", options=["Todos", *svc_values], key="_ap_cal_f_service")
    with cf3:
        st.selectbox("Estado", options=["Todos", *status_values], key="_ap_cal_f_status")

    cal_filtered = _apply_appointment_filters(
        items,
        use_date_range=False,
        name_key="_ap_cal_f_name",
        service_key="_ap_cal_f_service",
        status_key="_ap_cal_f_status",
    )
    hist_counts = _appointment_counts_by_client(items)
    by_day = _appointments_by_day_sorted(cal_filtered)
    _render_main_calendar(by_day, hist_counts)

    if st.session_state.get("_cal_overflow_day"):
        _dialog_calendar_day_appointments(by_day, hist_counts)
    if st.session_state.get("_ap_dlg") == "create":
        _dialog_agendar_cita()
