"""Vista semanal: rejilla horaria HTML (08:00–20:00, franjas 30 min)."""



from __future__ import annotations



import html as html_mod

from datetime import date, timedelta

from typing import Any, Callable



import streamlit as st



from streamlit_app.appointment_agenda_slots import duration_slots_for_existing_appointment

from streamlit_app.appointment_dates import appointment_time_hm

from streamlit_app.appointment_slots import time_slot_options

from streamlit_app.appointment_staff_labels import assigned_staff_label

from streamlit_app.components.calendar_cells import calendar_appt_total_chip_html
from streamlit_app.components.calendar_month_footer import calendar_week_header_book_strip_html
from streamlit_app.components.calendar_query_nav import calendar_appt_open_control_html
from app.domain.appointment_money import appointment_financial_totals, format_cop

from streamlit_app.components.pills import client_pill_class



__all__ = [

    "WEEK_SCHEDULE_SLOT_PX",

    "render_week_schedule_grid",

    "week_grid_html_for_week",

    "week_monday",

]





# Altura en px de cada franja de 30 min (hora + cliente + «Ver cita» en citas de 1 franja).

WEEK_SCHEDULE_SLOT_PX = 72





def week_monday(d: date) -> date:

    """Lunes como primer día de la semana (ISO: weekday() 0=lunes)."""

    return d - timedelta(days=d.weekday())





def _twg_day_header_book_html(d: date, today: date, *, allow_book: bool) -> str:
    """Pie «+ Agregar cita» bajo el día (mismo HTML/CSS que calendario mensual)."""
    if not allow_book:
        disabled = True
        title = "Los tatuadores y perforadores no pueden agendar desde el calendario"
    elif d < today:
        disabled = True
        title = "No se pueden agendar citas en fechas pasadas"
    else:
        disabled = False
        title = f"Agendar cita · {d.strftime('%d/%m/%Y')}"
    return calendar_week_header_book_strip_html(
        d.year,
        d.month,
        d.day,
        disabled_footer=disabled,
        title_esc=html_mod.escape(title),
    )





def week_grid_parse_segments(

    day_rows: list[dict[str, Any]],

    slot_list: list[str],

) -> list[tuple[dict[str, Any], int, int]]:

    """Citas posicionables en la rejilla: (row, start_idx, dur_slots_vis)."""

    n = len(slot_list)

    raw: list[tuple[dict[str, Any], int, int]] = []

    for row in day_rows:

        hm = appointment_time_hm(row.get("appointment_date", row.get("date")))

        if hm == "—":

            continue

        try:

            start_idx = slot_list.index(hm)

        except ValueError:

            continue

        dur = duration_slots_for_existing_appointment(row)

        end_idx = min(start_idx + dur, n)

        vis = max(0, end_idx - start_idx)

        if vis <= 0:

            continue

        raw.append((row, start_idx, vis))

    raw.sort(key=lambda x: (x[1], -x[2]))

    return raw





def week_grid_assign_lanes(

    raw: list[tuple[dict[str, Any], int, int]],

) -> list[tuple[dict[str, Any], int, int, int, int]]:

    """Asigna carril para solapes (greedy). Devuelve (row, start_idx, vis, lane_i, n_lanes)."""

    lanes_end: list[int] = []

    assignments: list[tuple[dict[str, Any], int, int, int]] = []

    for row, start_idx, vis in raw:

        end_idx = start_idx + vis

        lane_i = -1

        for li, le in enumerate(lanes_end):

            if start_idx >= le:

                lane_i = li

                lanes_end[li] = end_idx

                break

        if lane_i < 0:

            lane_i = len(lanes_end)

            lanes_end.append(end_idx)

        assignments.append((row, start_idx, vis, lane_i))

    n_lanes = max(1, len(lanes_end))

    return [(r, s, v, l, n_lanes) for r, s, v, l in assignments]





def week_grid_day_column_html(

    d: date,

    buckets: dict[tuple[int, int, int], list[dict[str, Any]]],

    counts_by_client: dict[str, int],

    *,

    slot_list: list[str],

    slot_px: int,

    today: date,

    monday_iso: str,

) -> str:

    """Columna de un día con líneas de tiempo y bloques absolutos."""

    n_slots = len(slot_list)

    total_h = n_slots * slot_px

    day_rows = list(buckets.get((d.year, d.month, d.day), []))

    raw_seg = week_grid_parse_segments(day_rows, slot_list)

    placed = week_grid_assign_lanes(raw_seg)

    today_cls = " twg-col-today" if d == today else ""

    parts: list[str] = [f'<div class="twg-col{today_cls}" style="height:{total_h}px">']

    for si in range(n_slots):

        parts.append(

            f'<div class="twg-slot-line" style="top:{si * slot_px}px;height:{slot_px}px"></div>'

        )

    for row, start_idx, vis, lane_i, n_lanes in placed:

        cls_pill = client_pill_class(row, counts_by_client)

        top = start_idx * slot_px

        height = max(vis * slot_px - 3, slot_px - 4)

        pct_w = 100.0 / n_lanes

        left = lane_i * pct_w

        nm = str(row.get("customer_name") or row.get("name") or "").strip() or "—"

        nm_esc = html_mod.escape(nm)

        hm = appointment_time_hm(row.get("appointment_date", row.get("date")))

        staff = assigned_staff_label(row)
        total_amt, _, _ = appointment_financial_totals(row)
        staff_part = f" · {staff}" if staff != "—" else ""
        tit = html_mod.escape(f"{hm} · {nm}{staff_part} · Total: {format_cop(total_amt)}")

        st_cl = str(row.get("status") or "").strip().lower()

        soft_cls = " twg-cancelada-soft" if st_cl == "cancelada" else ""

        ap_id = int(row.get("id", 0) or 0)

        single_slot = vis <= 1

        link_html = ""
        if ap_id > 0:
            link_html = calendar_appt_open_control_html(
                ap_id, extra_class="twg-appt-link", monday_iso=monday_iso
            )

        cls_appt_extra = " twg-appt--single-slot" if single_slot else ""

        body = (
            '<div class="twg-appt-body-stack">'
            f'<span class="twg-appt-head-time">{html_mod.escape(hm)}</span>'
            f'<span class="twg-appt-client">{nm_esc}</span>'
            f"{calendar_appt_total_chip_html(row)}"
            "</div>"
        )

        geo = (

            f"top:{top}px;height:{height}px;left:{left}%;width:calc({pct_w}% - 3px);margin-left:1px"

        )

        parts.append(

            f'<div class="twg-appt twg-{cls_pill}{cls_appt_extra}{soft_cls}" '

            f'title="{tit}" style="{geo}">{body}{link_html}</div>'

        )

    parts.append("</div>")

    return "".join(parts)





def week_grid_html_for_week(

    monday: date,

    buckets: dict[tuple[int, int, int], list[dict[str, Any]]],

    counts_by_client: dict[str, int],

    *,

    slot_list: list[str],

    slot_px: int,

    allow_book: bool,

) -> str:

    """HTML de la rejilla semanal completa (cabecera + cuerpo)."""

    today = date.today()

    monday_iso = monday.isoformat()

    weekdays_short = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

    parts: list[str] = ['<div class="twg-shell"><div class="twg-scroll-x"><div class="twg-grid-wrap">']



    parts.append('<div class="twg-head">')

    parts.append('<div class="twg-h-spacer"></div>')

    parts.append('<div class="twg-h-days">')

    for i in range(7):

        d = monday + timedelta(days=i)

        today_cls = " twg-h-today" if d == today else ""

        book_html = _twg_day_header_book_html(d, today, allow_book=allow_book)

        parts.append(

            f'<div class="twg-h-day{today_cls}">'

            f'<div class="twg-h-wd">{weekdays_short[i]}</div>'

            f'<div class="twg-h-num">{d.day}</div>'

            f"{book_html}"

            "</div>"

        )

    parts.append("</div></div>")



    parts.append('<div class="twg-body">')

    parts.append('<div class="twg-times">')

    for hm in slot_list:

        is_hour = hm.endswith(":00")

        cls = "twg-tick-major" if is_hour else "twg-tick-minor"

        label = hm if is_hour else ""

        parts.append(f'<div class="twg-tick {cls}" style="height:{slot_px}px"><span>{label}</span></div>')

    parts.append("</div>")

    parts.append('<div class="twg-day-columns">')

    for i in range(7):

        d = monday + timedelta(days=i)

        parts.append(

            week_grid_day_column_html(

                d,

                buckets,

                counts_by_client,

                slot_list=slot_list,

                slot_px=slot_px,

                today=today,

                monday_iso=monday_iso,

            )

        )

    parts.append("</div></div>")

    parts.append("</div></div></div>")

    return "".join(parts)





def render_week_schedule_grid(

    buckets: dict[tuple[int, int, int], list[dict[str, Any]]],

    counts_by_client: dict[str, int],

    *,

    clear_calendar_dialog_focus: Callable[[], None],

    panel_is_technician_role: Callable[[], bool],

    pop_booking_document_session: Callable[[], None],

) -> None:

    """Vista semanal con columnas por día y bloques proporcionales a la duración (30 min/slot)."""

    anchor_key = "_ap_week_monday"

    if anchor_key not in st.session_state:

        st.session_state[anchor_key] = week_monday(date.today()).isoformat()

    try:

        monday = date.fromisoformat(str(st.session_state[anchor_key]))

    except ValueError:

        monday = week_monday(date.today())

        st.session_state[anchor_key] = monday.isoformat()



    st.markdown("##### Agenda semanal (rejilla horaria)")



    b1, b2, b3, b4 = st.columns([1.1, 1.1, 3.2, 1.1])

    with b1:

        if st.button("◀ Semana", key="twg_prev_week"):

            clear_calendar_dialog_focus()

            st.session_state[anchor_key] = (monday - timedelta(days=7)).isoformat()

            st.rerun()

    with b2:

        if st.button("Hoy", key="twg_today_week"):

            clear_calendar_dialog_focus()

            st.session_state[anchor_key] = week_monday(date.today()).isoformat()

            st.rerun()

    with b3:

        sunday = monday + timedelta(days=6)

        span_lbl = f"{monday.strftime('%d/%m')} – {sunday.strftime('%d/%m/%Y')}"

        st.markdown(

            f"<div style='text-align:center;font-weight:600;padding-top:0.35rem'>"

            f"{html_mod.escape(span_lbl)}</div>",

            unsafe_allow_html=True,

        )

    with b4:

        if st.button("Semana ▶", key="twg_next_week"):

            clear_calendar_dialog_focus()

            st.session_state[anchor_key] = (monday + timedelta(days=7)).isoformat()

            st.rerun()



    allow_book = not panel_is_technician_role()

    slot_list = time_slot_options()

    st.markdown(
        week_grid_html_for_week(
            monday,
            buckets,
            counts_by_client,
            slot_list=slot_list,
            slot_px=WEEK_SCHEDULE_SLOT_PX,
            allow_book=allow_book,
        ),
        unsafe_allow_html=True,
    )

