"""PDF de recibo de abono: orden de trabajo maquetada en código (A4), alineada al diseño Rock City.

Cabecera negra (datos comerciales + orden/fecha), bloque de formulario en gris oscuro con inputs blancos redondeados
y etiquetas dentro de cada campo, franja roja y condiciones legales debajo.

Personalización opcional vía entorno:
- PAYMENT_RECEIPT_LOGO_IMAGE — ruta a PNG del logo (centrado en cabecera). Si no hay archivo, se intenta `app/assets/receipt_rock_city_logo.png`.
- PAYMENT_RECEIPT_CONTACT_IMAGE — ruta a PNG del bloque comercial (izquierda). Si no hay archivo, se pinta texto en blanco en negrita.
- PAYMENT_RECEIPT_ADDR_LINE1, PAYMENT_RECEIPT_ADDR_LINE2 — dirección si no usas imagen de contacto.
- PAYMENT_RECEIPT_WHATSAPP — solo número; se muestra como «WHATSAPP …».
- PAYMENT_RECEIPT_CONTACT_LINE — línea opcional al pie (además de la fecha de generación).
- PAYMENT_RECEIPT_TERMS_EMAIL, PAYMENT_RECEIPT_TERMS_PHONE — correo y teléfono del párrafo final de envío de diseños.
- PAYMENT_RECEIPT_LOGO_LINE1, PAYMENT_RECEIPT_LOGO_LINE2, PAYMENT_RECEIPT_LOGO_MARK — solo si **no** hay PNG de logo (texto de respaldo).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
from typing import Optional

import fitz  # PyMuPDF

_AGENDA_SLOTS_DETAIL_PATTERN = re.compile(r"\s*\[agenda_slots:\d+\]\s*$", re.IGNORECASE)
# Etiquetas tipo «[Tatuaje]» que no deben repetirse en el campo DISEÑO (el tipo ya va en BD como service_type).
_LEADING_BRACKET_SERVICE_LABEL = re.compile(r"^\s*(?:\[[^\]]+\]\s*)+")
# Mismo patrón en cualquier parte del detalle (no solo al inicio).
_SERVICE_BRACKET_IN_TEXT = re.compile(
    r"\[\s*(?:Tatuaje|Piercing|Cambio|Limpieza)\s*\]",
    re.IGNORECASE,
)
# Palabra suelta al inicio del detalle (mismo tipo que en service_type; no repetir en DISEÑO).
_SERVICE_WORD_LEADING = re.compile(
    r"^\s*(?:Tatuaje|Piercing|Cambio|Limpieza)\b\s*",
    re.IGNORECASE,
)

PAYMENT_RECEIPT_N8N_TEMPLATE_KEY = "orden_trabajo_rock_city"

_PAGE = fitz.paper_rect("a4")
PAGE_W = _PAGE.width
PAGE_H = _PAGE.height

_BLACK = (0.0, 0.0, 0.0)
_WHITE = (1.0, 1.0, 1.0)
_INK = (0.0, 0.0, 0.0)
_RED = (1.0, 0.0, 0.0)
# Franja inferior tipo lámina impresa (#E31E24).
_RED_STRIP = (227 / 255, 30 / 255, 36 / 255)
# Zona de formulario (#2B2B2B).
_FORM_GRAY = (43 / 255, 43 / 255, 43 / 255)
_BOX_EDGE = (0.78, 0.78, 0.78)
# Rojo del sello 纹身 en referencia de marca (~#E53E3E), solo si el logo va como texto.
_MARK_RED_UI = (229 / 255, 62 / 255, 62 / 255)

# Textos tomados de la lámina de muestra (franja roja y condiciones).
_ATTENTION_TEXT = (
    "ATENCIÓN: SI NO PUEDE ASISTIR A LA CITA, LLÁMENOS CON HORAS DE ANTICIPACIÓN.\n"
    "NUESTRO TIEMPO VALE TANTO COMO EL SUYO."
)

_TERMS_LINES: tuple[str, ...] = (
    "NO HAY DEVOLUCIONES DE DINERO DE ABONOS DE CITAS CANCELADAS",
    "DESPUÉS DE CANCELAR SU CITA DOS VECES PERDERÁ EL VALOR ABONADO",
    "TODO ABONO ES INTRANSFERIBLE",
    "PARA MENORES DE EDAD, PRESENTARSE CON SU ACUDIENTE ÚNICAMENTE PADRE Y/O MADRE, "
    "CON ORIGINAL Y COPIA DE LOS DOCUMENTOS DE IDENTIFICACIÓN.",
    "EL PLAZO MÁXIMO PARA REALIZAR UN TATUAJE Y/O PERORACIÓN ES DE 60 DÍAS CALENDARIO.",
    "PARA CUALQUIER CAMBIO O RECLAMO DEBE PRESENTAR ESTE DOCUMENTO.",
    "LA GARANTÍA DE SU TATUAJE, SERA CUBIERTA HASTA UN MES CALENDARIO, DESPUÉS DE REALIZADO EL MISMO, "
    "PASADO ESTE TIEMPO, USTED PERDERA LA GARANTÍA EN MENCIÓN.",
    "LA GARANTÍA CUBRE POR FALTA DE RELLENO Y LINEAS INCOMPLETAS, MAS NO POR DESCUIDO O INCUMPLIMIENTO "
    "EN LA FORMA DE CUIDARLO, RECUERDE QUE ESTE ES UN TRABAJO ARTESANAL.",
)

# Política adicional (segunda lámina / confirmación de cita), tipografía mayúsculas como en el original.
_POLICY_CONFIRMATION: tuple[tuple[str, bool, tuple[float, float, float]], ...] = (
    (
        "USTED SERÁ, CONTACTADO UN DÍA ANTES DE SU TATUAJE, POR VÍA TELEFÓNICA, WHATSAPP, "
        "CORREO ELECTRÓNICO Y/O MENSAJE DE VOZ, (ESTOS TRES ÚLTIMOS SI USTED NO RESPONDE NUESTRA LLAMADA), "
        "EN ELLOS SE DEJARA UN MENSAJE, INFORMANDOLE HASTA QUE HORA TIENE USTED PLAZO DE COMUNICARSE CON "
        "NOSOTROS PARA CONFIRMAR O CANCELAR SU CITA, SI USTED NO SE COMUNICA, DAMOS POR ENTENDIDO QUE NO "
        "PUEDE ASISTIR, Y SU CITA SERA CANCELADA.",
        True,
        _INK,
    ),
    (
        "SI USTED CONFIRMA LA CITA A SU TATUAJE Y NO ASISTE, PERDERÁ EL VALOR ABONADO.",
        True,
        _INK,
    ),
    (
        "EL DÍA DE LA CITA, USTED TIENE UN PLAZO HASTA DE 20 MINUTOS DESPUÉS DE LA HORA PROGRAMADA PARA "
        "ASISTIR A LA MISMA, DESPUÉS DE ESE TIEMPO SU CITA SERA CANCELADA.",
        True,
        _INK,
    ),
    (
        "SI USTED POR ALGÚN MOTIVO CANCELA SU CITA, PARA ASIGNAR UNA NUEVA FECHA, DEBE REALIZAR OTRO ABONO .",
        False,
        _RED,
    ),
)

_POLICY_DESIGN_PREFIX = (
    "RECUERDE QUE LA IDEA PRINCIPAL, IMÁGENES DEL PROYECTO, FOTOGRAFÍAS, CAMBIOS EN DISEÑO, Y/O FORMA, "
    "DEBEN SER ENVIADAS POR LO MENOS UN DIA ANTERIOR A SU CITA, AL CORREO ELECTRONICO "
)

_POLICY_DESIGN_MIDDLE = (
    " Y RECONFIRMANDO SU ENVIO AL NUMERO TELEFONICO "
)


def _terms_contact_email() -> str:
    return (os.getenv("PAYMENT_RECEIPT_TERMS_EMAIL") or "rockcity72@gmail.com").strip()


def _terms_contact_phone() -> str:
    return (os.getenv("PAYMENT_RECEIPT_TERMS_PHONE") or "3209259415").strip()


def _addr_lines() -> tuple[str, str]:
    a1 = (os.getenv("PAYMENT_RECEIPT_ADDR_LINE1") or "CRA 34 # 51 - 56").strip()
    a2 = (os.getenv("PAYMENT_RECEIPT_ADDR_LINE2") or "BUCARAMANGA - COLOMBIA").strip()
    return a1, a2


def _whatsapp_line() -> str:
    # Número de la lámina comercial Rock City Bucaramanga (sobreescribible por entorno).
    num = (os.getenv("PAYMENT_RECEIPT_WHATSAPP") or "3112157817").strip()
    return f"WHATSAPP {num}"


def _logo_lines() -> tuple[str, str]:
    line1 = (os.getenv("PAYMENT_RECEIPT_LOGO_LINE1") or "ROCK CITY").strip()
    line2 = (os.getenv("PAYMENT_RECEIPT_LOGO_LINE2") or "TATTOO - PIERCING").strip()
    return line1, line2


def _logo_mark() -> str:
    """Texto rojo bajo el subtítulo (p. ej. 纹身). Cadena vacía en entorno = no mostrar."""
    v = os.getenv("PAYMENT_RECEIPT_LOGO_MARK")
    if v is None:
        return "纹身"
    return v.strip()


def _contact_line() -> str:
    return (os.getenv("PAYMENT_RECEIPT_CONTACT_LINE") or "").strip()


def _assets_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "assets"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_payment_receipt_logo_png() -> Optional[str]:
    """Primera ruta existente: env → app/assets → streamlit_app/assets."""
    raw = (os.getenv("PAYMENT_RECEIPT_LOGO_IMAGE") or "").strip()
    candidates: list[Path] = []
    if raw:
        candidates.append(Path(raw))
    ad = _assets_dir()
    candidates.extend(
        [
            ad / "receipt_rock_city_logo.png",
            ad / "receipt_logo.png",
            _repo_root() / "streamlit_app" / "assets" / "receipt_rock_city_logo.png",
            _repo_root() / "streamlit_app" / "assets" / "rock_city_watermark.png",
        ]
    )
    for p in candidates:
        if p.is_file():
            return str(p.resolve())
    return None


def resolve_payment_receipt_contact_png() -> Optional[str]:
    raw = (os.getenv("PAYMENT_RECEIPT_CONTACT_IMAGE") or "").strip()
    candidates: list[Path] = []
    if raw:
        candidates.append(Path(raw))
    ad = _assets_dir()
    candidates.extend([ad / "receipt_rock_city_contact.png", ad / "receipt_contact.png"])
    for p in candidates:
        if p.is_file():
            return str(p.resolve())
    return None


def _insert_image_cover(page: fitz.Page, rect: fitz.Rect, path: str) -> bool:
    try:
        page.insert_image(rect, filename=path, keep_proportion=True)
        return True
    except (RuntimeError, ValueError, AttributeError):
        return False


def _fmt_cop(n: float) -> str:
    n = float(n)
    s = f"{n:,.2f}"
    return "$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def _clean_design_notes(detail: str) -> str:
    """Quita marcadores internos de agenda del texto mostrado como «Diseño / notas»."""
    return _AGENDA_SLOTS_DETAIL_PATTERN.sub("", detail or "").strip()


def _clean_detail_for_design(detail: str) -> str:
    """Limpia detalle de cita para el campo DISEÑO (incluye «[Tatuaje]» en cualquier posición)."""
    s = _clean_design_notes(detail or "")
    s = _SERVICE_BRACKET_IN_TEXT.sub("", s)
    s = _LEADING_BRACKET_SERVICE_LABEL.sub("", s).strip()
    while True:
        t = _SERVICE_WORD_LEADING.sub("", s).strip()
        if t == s:
            break
        s = t
    return " ".join(s.split()).strip()


def _skip_payment_note_in_design(note: str) -> bool:
    """Notas estándar del movimiento de pago que no deben repetirse en el campo DISEÑO."""
    n = " ".join((note or "").strip().split()).casefold()
    return n in {
        "abono inicial al agendar",
        "abono inicial al agenda",
    }


def _clock_12h_ampm(hour: int, minute: int) -> str:
    h = int(hour) % 24
    mi = int(minute) % 60
    ampm = "AM" if h < 12 else "PM"
    h12 = h % 12
    if h12 == 0:
        h12 = 12
    return f"{h12}:{mi:02d} {ampm}"


def _appointment_cita_y_hora(raw: str) -> tuple[str, str]:
    """Devuelve (cita en dd-mm-yyyy, hora 12 h con AM/PM) a partir del DATETIME de la cita en BD/T API."""
    s = (raw or "").strip().replace("T", " ")
    if not s:
        return "", ""
    parts = s.split()
    date_part = parts[0]
    time_part = parts[1] if len(parts) > 1 else ""
    dd_mm_yyyy = date_part
    try:
        if len(date_part) == 10 and date_part[4] == "-" and date_part[7] == "-":
            y, m, d = date_part.split("-")
            dd_mm_yyyy = f"{int(d):02d}-{int(m):02d}-{y}"
    except ValueError:
        pass
    hora = ""
    if time_part:
        hms = time_part.split(":")
        if len(hms) >= 2:
            try:
                hora = _clock_12h_ampm(int(hms[0]), int(hms[1]))
            except ValueError:
                hora = ""
    return dd_mm_yyyy, hora


def _issued_dma(issued_at: datetime) -> tuple[str, str, str]:
    return f"{issued_at.day:02d}", f"{issued_at.month:02d}", f"{issued_at.year:04d}"


def _issued_dd_mm_yyyy(issued_at: datetime) -> str:
    return f"{issued_at.day:02d}/{issued_at.month:02d}/{issued_at.year:04d}"


def _issued_time_hm(issued_at: datetime) -> str:
    return _clock_12h_ampm(issued_at.hour, issued_at.minute)


def _split_abono_amounts_for_boxes(amounts: list[float]) -> tuple[str, str, str]:
    fmt = [_fmt_cop(a) for a in amounts]
    if not fmt:
        return "", "", ""
    if len(fmt) == 1:
        return fmt[0], "", ""
    if len(fmt) == 2:
        return fmt[0], fmt[1], ""
    if len(fmt) == 3:
        return fmt[0], fmt[1], fmt[2]
    return fmt[0], fmt[1], "\n".join(fmt[2:])


def _lbl_black_header(page: fitz.Page, rect: fitz.Rect, text: str, *, fontsize: float = 8.0, bold: bool = True) -> None:
    page.insert_textbox(
        rect,
        text,
        fontsize=fontsize,
        fontname="hebo" if bold else "helv",
        color=_WHITE,
        align=fitz.TEXT_ALIGN_LEFT,
    )


def _draw_round_rect(
    page: fitz.Page,
    rect: fitz.Rect,
    *,
    radius_pct: float = 0.38,
    fill: tuple[float, float, float] | None = None,
    stroke: tuple[float, float, float] | None = None,
    width: float = 0.3,
) -> None:
    """Rectángulo con esquinas redondeadas (`radius_pct` 0–0.5 relativo al lado corto)."""
    shape = page.new_shape()
    shape.draw_rect(rect, radius=radius_pct)
    sw = width if stroke is not None else 0
    shape.finish(fill=fill, color=stroke, width=sw)
    shape.commit()


def _textbox_shrink_to_fit(
    page: fitz.Page,
    rect: fitz.Rect,
    text: str,
    *,
    fontsize: float,
    fontname: str,
    color: tuple[float, float, float],
    align: int = fitz.TEXT_ALIGN_LEFT,
    min_fs: float = 6.0,
    step: float = 0.35,
) -> None:
    """insert_textbox devuelve espacio sobrante negativo si la caja es demasiado baja para el tamaño pedido."""
    t = (text or "").strip() or "-"
    fs = float(fontsize)
    while fs >= min_fs:
        leftover = page.insert_textbox(rect, t, fontsize=fs, fontname=fontname, color=color, align=align)
        if leftover >= 0:
            return
        fs -= step
    page.insert_textbox(rect, t, fontsize=min_fs, fontname=fontname, color=color, align=align)


def _field_inline(
    page: fitz.Page,
    rect: fitz.Rect,
    label: str,
    value: str,
    *,
    label_width: float = 54.0,
    fs_label: float = 7.65,
    fs_val: float = 9.0,
    val_bold: bool = False,
    radius_pct: float = 0.42,
) -> None:
    """Campo blanco redondeado con la etiqueta dentro a la izquierda y el valor a la derecha."""
    _draw_round_rect(page, rect, radius_pct=radius_pct, fill=_WHITE, stroke=_BOX_EDGE, width=0.28)
    pad_x, pad_y = 6.0, 3.5
    rl = fitz.Rect(rect.x0 + pad_x, rect.y0 + pad_y, rect.x0 + pad_x + label_width, rect.y1 - pad_y)
    rv = fitz.Rect(rect.x0 + pad_x + label_width + 2.0, rect.y0 + pad_y, rect.x1 - pad_x, rect.y1 - pad_y)
    _textbox_shrink_to_fit(
        page,
        rl,
        label,
        fontsize=fs_label,
        fontname="hebo",
        color=_INK,
        align=fitz.TEXT_ALIGN_LEFT,
    )
    fn = "hebo" if val_bold else "helv"
    _textbox_shrink_to_fit(
        page,
        rv,
        (value or "").strip() or "-",
        fontsize=fs_val,
        fontname=fn,
        color=_INK,
        align=fitz.TEXT_ALIGN_LEFT,
    )


def _header_white_chip(page: fitz.Page, rect: fitz.Rect, text: str, *, fontsize: float = 10.0, bold: bool = True) -> None:
    """Recuadro blanco redondeado sobre fondo negro (orden, fecha D/M/A)."""
    _draw_round_rect(page, rect, radius_pct=0.48, fill=_WHITE, stroke=_BOX_EDGE, width=0.22)
    pad_x, pad_y = 3.0, 2.5
    inner = fitz.Rect(rect.x0 + pad_x, rect.y0 + pad_y, rect.x1 - pad_x, rect.y1 - pad_y)
    fn = "hebo" if bold else "helv"
    _textbox_shrink_to_fit(
        page,
        inner,
        (text or "").strip() or "-",
        fontsize=fontsize,
        fontname=fn,
        color=_INK,
        align=fitz.TEXT_ALIGN_CENTER,
        min_fs=6.0,
        step=0.35,
    )


def _fmt_money_cell(s: str) -> str:
    return s if (s or "").strip() else "-"


def _terms_page_bottom() -> float:
    """Tope vertical antes del pie reservado para «Documento generado…»."""
    return PAGE_H - 52


def _emit_terms_paragraph(
    doc: fitz.Document,
    page: fitz.Page,
    y: float,
    mx: float,
    body: str,
    *,
    bullet: bool,
    color: tuple[float, float, float],
    fontsize: float = 8.15,
    gap_after: float = 10.0,
) -> tuple[fitz.Page, float]:
    """Pinta un párrafo (opcional guión «- ») justificado y devuelve la página activa y la Y siguiente."""
    x0 = mx + 2
    x1 = PAGE_W - mx - 2
    # Helvetica integrada no incluye «•» (U+2022); en PDF aparece como «?». Usar ASCII.
    full = f"- {body}" if bullet else body
    limit_y = _terms_page_bottom()

    def _new_sheet() -> tuple[fitz.Page, float]:
        p = doc.new_page(width=PAGE_W, height=PAGE_H)
        return p, 36.0

    if y > limit_y - 44:
        page, y = _new_sheet()
    avail = limit_y - y - 6
    if avail < 42:
        page, y = _new_sheet()
        avail = limit_y - y - 6
    rect_h = min(300.0, avail)
    r = fitz.Rect(x0, y, x1, y + rect_h)
    fs = fontsize
    rv = -1.0
    while fs >= 6.45:
        rv = page.insert_textbox(
            r,
            full,
            fontsize=fs,
            fontname="helv",
            color=color,
            align=fitz.TEXT_ALIGN_JUSTIFY,
        )
        if rv >= 0:
            advance = rect_h - rv
            return page, y + max(advance, fs * 1.15) + gap_after
        fs -= 0.28
    page.insert_textbox(
        r,
        full,
        fontsize=6.35,
        fontname="helv",
        color=color,
        align=fitz.TEXT_ALIGN_JUSTIFY,
    )
    return page, y + rect_h + gap_after


def _emit_design_delivery_paragraph(
    doc: fitz.Document,
    page: fitz.Page,
    y: float,
    mx: float,
) -> tuple[fitz.Page, float]:
    """Último bloque de política: texto + correo y teléfono en negrita."""
    email = _terms_contact_email()
    phone = _terms_contact_phone()
    segments: tuple[tuple[str, bool, float], ...] = (
        (_POLICY_DESIGN_PREFIX, False, 8.05),
        (email, True, 8.35),
        (_POLICY_DESIGN_MIDDLE, False, 8.05),
        (phone, True, 8.35),
    )
    x0 = mx + 2
    x1 = PAGE_W - mx - 2
    limit_y = _terms_page_bottom()
    gap_small = 5.0

    def _new_sheet() -> tuple[fitz.Page, float]:
        p = doc.new_page(width=PAGE_W, height=PAGE_H)
        return p, 36.0

    for text, bold, fs in segments:
        if y > limit_y - 32:
            page, y = _new_sheet()
        avail = limit_y - y - 6
        if avail < 26:
            page, y = _new_sheet()
            avail = limit_y - y - 6
        rect_h = min(220.0 if not bold else 40.0, avail)
        r = fitz.Rect(x0, y, x1, y + rect_h)
        fn = "hebo" if bold else "helv"
        rv = page.insert_textbox(
            r,
            text,
            fontsize=fs,
            fontname=fn,
            color=_INK,
            align=fitz.TEXT_ALIGN_JUSTIFY if not bold else fitz.TEXT_ALIGN_LEFT,
        )
        if rv < 0:
            rr = fitz.Rect(x0, y, x1, y + min(avail, 320.0))
            page.insert_textbox(
                rr,
                text,
                fontsize=max(6.0, fs - 0.5),
                fontname=fn,
                color=_INK,
                align=fitz.TEXT_ALIGN_JUSTIFY if not bold else fitz.TEXT_ALIGN_LEFT,
            )
            y = rr.y1 + gap_small
        else:
            advance = rect_h - rv
            y = y + max(advance, fs * 1.12) + gap_small

    return page, y + 6


def _render_terms_blocks(doc: fitz.Document, page: fitz.Page, y: float, mx: float) -> fitz.Page:
    """Condiciones generales + política de confirmación/cita (varias páginas si hace falta)."""
    for line in _TERMS_LINES:
        page, y = _emit_terms_paragraph(doc, page, y, mx, line, bullet=True, color=_INK)
    y += 4
    for body, bullet, col in _POLICY_CONFIRMATION:
        page, y = _emit_terms_paragraph(doc, page, y, mx, body, bullet=bullet, color=col)
    page, _y = _emit_design_delivery_paragraph(doc, page, y, mx)
    return page


@dataclass
class PaymentReceiptPdfContext:
    """Contexto para rellenar la orden de trabajo / recibo de abono."""

    client_name: str
    client_phone: str
    appointment_when: str
    service: str
    detail: str
    total_amount: float
    this_payment: float
    deposit_total_after: float
    pending_after: float
    kind_label: str
    issued_at: datetime
    payment_note: Optional[str] = None
    appointment_id: int = 0
    client_email: str = ""
    payment_history: list[tuple[float, Optional[str]]] = field(default_factory=list)


def build_payment_receipt_pdf(ctx: PaymentReceiptPdfContext) -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)

    mx = 26.0
    inner_w = PAGE_W - 2 * mx

    header_h = 80.0
    gray_pad_v = 7.0
    row_h = 22.0
    row_gap = 5.0
    dis_h = 38.0
    gap_mid = 9.0
    banner_h = 34.0

    inner_top = header_h + gray_pad_v
    y1 = inner_top
    y2 = y1 + row_h + row_gap
    y3 = y2 + row_h + row_gap
    y4 = y3 + dis_h + row_gap
    y5 = y4 + row_h
    sys_top = y5 + 6.0
    form_bottom = sys_top + 13.0 + gray_pad_v

    gray_top = header_h
    page.draw_rect(fitz.Rect(0, gray_top, PAGE_W, form_bottom), color=_FORM_GRAY, fill=_FORM_GRAY, width=0)
    page.draw_rect(fitz.Rect(0, 0, PAGE_W, header_h), color=_BLACK, fill=_BLACK, width=0)

    rx0 = PAGE_W - mx - 184
    contact_rect = fitz.Rect(mx + 2, 6, mx + 178, header_h - 5)
    logo_rect = fitz.Rect(mx + 186, 5, rx0 - 12, header_h - 5)

    a1, a2 = _addr_lines()
    contact_png = resolve_payment_receipt_contact_png()
    if not contact_png or not _insert_image_cover(page, contact_rect, contact_png):
        commercial_txt = f"{a1.upper()}\n{a2.upper()}\n{_whatsapp_line().upper()}"
        page.insert_textbox(
            contact_rect,
            commercial_txt,
            fontsize=9.0,
            fontname="hebo",
            color=_WHITE,
            align=fitz.TEXT_ALIGN_LEFT,
        )

    logo_png = resolve_payment_receipt_logo_png()
    if not logo_png or not _insert_image_cover(page, logo_rect, logo_png):
        logo1, logo2 = _logo_lines()
        page.insert_textbox(
            fitz.Rect(logo_rect.x0, 10, logo_rect.x1, 36),
            logo1.upper(),
            fontsize=14.8,
            fontname="hebo",
            color=_WHITE,
            align=fitz.TEXT_ALIGN_CENTER,
        )
        page.insert_textbox(
            fitz.Rect(logo_rect.x0, 32, logo_rect.x1, 48),
            logo2.upper(),
            fontsize=8.85,
            fontname="helv",
            color=_WHITE,
            align=fitz.TEXT_ALIGN_CENTER,
        )
        mark = _logo_mark()
        if mark:
            page.insert_textbox(
                fitz.Rect(logo_rect.x0, 47, logo_rect.x1, header_h - 6),
                mark,
                fontsize=11.2,
                fontname="helv",
                color=_MARK_RED_UI,
                align=fitz.TEXT_ALIGN_CENTER,
            )

    _lbl_black_header(page, fitz.Rect(rx0, 15, rx0 + 86, 29), "ORDEN DE TRABAJO", fontsize=6.85)
    chip_ord = fitz.Rect(rx0 + 88, 13, PAGE_W - mx - 2, 31)
    ord_txt = str(int(ctx.appointment_id)) if ctx.appointment_id else "-"
    _header_white_chip(page, chip_ord, ord_txt, fontsize=9.8, bold=True)

    _lbl_black_header(page, fitz.Rect(rx0, 36, rx0 + 34, 48), "FECHA", fontsize=7.5)
    d_str, m_str, y_str = _issued_dma(ctx.issued_at)
    bx = rx0 + 38
    bw, bh, g = 32.0, 21.0, 4.0
    for i, lab in enumerate(("D", "M", "A")):
        xb = bx + i * (bw + g)
        page.insert_textbox(
            fitz.Rect(xb, 35, xb + bw, 43),
            lab,
            fontsize=7.1,
            fontname="hebo",
            color=_WHITE,
            align=fitz.TEXT_ALIGN_CENTER,
        )
        cell = fitz.Rect(xb, 45, xb + bw, 45 + bh)
        val = (d_str, m_str, y_str)[i]
        _header_white_chip(page, cell, val, fontsize=9.0 if i < 2 else 8.5, bold=(i == 2))

    tw = (inner_w - 2 * gap_mid) / 3
    x_a = mx
    x_b = mx + tw + gap_mid
    x_c = mx + 2 * (tw + gap_mid)
    cita_str, hora_str = _appointment_cita_y_hora(ctx.appointment_when)

    w_nom = inner_w * 0.685
    r_nom = fitz.Rect(mx, y1, mx + w_nom, y1 + row_h)
    _field_inline(page, r_nom, "NOMBRE:", ctx.client_name or "-", label_width=54.0, fs_val=9.4, radius_pct=0.44)
    r_cel = fitz.Rect(r_nom.x1 + gap_mid, y1, PAGE_W - mx, y1 + row_h)
    _field_inline(page, r_cel, "CEL:", ctx.client_phone or "-", label_width=34.0, fs_val=9.4, radius_pct=0.44)

    rc = fitz.Rect(x_a, y2, x_a + tw, y2 + row_h)
    _field_inline(page, rc, "CITA:", cita_str or "-", label_width=38.0, fs_val=9.0, radius_pct=0.42)
    rh = fitz.Rect(x_b, y2, x_b + tw, y2 + row_h)
    _field_inline(page, rh, "HORA:", hora_str or "-", label_width=40.0, fs_val=9.2, radius_pct=0.42)
    rem = fitz.Rect(x_c, y2, PAGE_W - mx, y2 + row_h)
    _field_inline(page, rem, "E-MAIL:", ctx.client_email or "-", label_width=48.0, fs_val=8.6, radius_pct=0.42)

    r_dis = fitz.Rect(mx, y3, PAGE_W - mx, y3 + dis_h)
    diseno_parts: list[str] = []
    body_d = _clean_detail_for_design(ctx.detail or "")
    if body_d:
        diseno_parts.append(body_d)
    note = (ctx.payment_note or "").strip()
    if note and not _skip_payment_note_in_design(note):
        diseno_parts.append(f"Nota: {note}")
    diseno_txt = "\n".join(diseno_parts).strip() or "-"
    if len(diseno_txt) > 1400:
        diseno_txt = diseno_txt[:1397] + "..."
    _field_inline(
        page,
        r_dis,
        "DISEÑO:",
        diseno_txt,
        label_width=56.0,
        fs_label=7.55,
        fs_val=7.85,
        radius_pct=0.28,
    )

    bw4 = (inner_w - 3 * gap_mid) / 4
    amounts = [float(a) for a, _ in ctx.payment_history]
    if not amounts and float(ctx.this_payment or 0) > 0:
        amounts = [float(ctx.this_payment)]
    a1s, a2s, a3s = _split_abono_amounts_for_boxes(amounts)
    fs_ab = 7.85 if len(amounts) > 3 else 8.85

    specs = [
        ("PRECIO $", _fmt_cop(ctx.total_amount), True),
        ("ABONO 1 $", _fmt_money_cell(a1s), False),
        ("ABONO 2 $", _fmt_money_cell(a2s), False),
        ("ABONO 3 $", _fmt_money_cell(a3s), False),
    ]
    for i, (lab, val, bold_price) in enumerate(specs):
        x0 = mx + i * (bw4 + gap_mid)
        rr = fitz.Rect(x0, y4, x0 + bw4, y4 + row_h)
        lw = 52.0 if i else 50.0
        _field_inline(
            page,
            rr,
            lab,
            val,
            label_width=lw,
            fs_label=7.35,
            fs_val=fs_ab if i else 9.0,
            val_bold=bold_price,
            radius_pct=0.4,
        )

    sys_line = (
        f"{ctx.kind_label} · Abonado acum.: {_fmt_cop(ctx.deposit_total_after)} · "
        f"Pendiente: {_fmt_cop(ctx.pending_after)} · Emitido {_issued_dd_mm_yyyy(ctx.issued_at)} "
        f"{_issued_time_hm(ctx.issued_at)}"
    )
    page.insert_textbox(
        fitz.Rect(mx + 2, sys_top, PAGE_W - mx - 2, sys_top + 13),
        sys_line,
        fontsize=6.35,
        fontname="helv",
        color=(0.72, 0.72, 0.72),
        align=fitz.TEXT_ALIGN_LEFT,
    )

    banner_y0 = form_bottom
    page.draw_rect(fitz.Rect(0, banner_y0, PAGE_W, banner_y0 + banner_h), color=_RED_STRIP, fill=_RED_STRIP, width=0)
    page.insert_textbox(
        fitz.Rect(mx + 8, banner_y0 + 4, PAGE_W - mx - 8, banner_y0 + banner_h - 4),
        _ATTENTION_TEXT,
        fontsize=7.45,
        fontname="hebo",
        color=_WHITE,
        align=fitz.TEXT_ALIGN_CENTER,
    )

    body_top = banner_y0 + banner_h + 14.0
    last_terms_page = _render_terms_blocks(doc, page, body_top, mx)

    foot_bits = [
        f"Documento generado el {_issued_dd_mm_yyyy(ctx.issued_at)} a las {_issued_time_hm(ctx.issued_at)}"
    ]
    extra = _contact_line()
    if extra:
        foot_bits.append(extra)
    foot = " · ".join(foot_bits)
    last_terms_page.insert_textbox(
        fitz.Rect(mx, PAGE_H - 38, PAGE_W - mx, PAGE_H - 14),
        foot,
        fontsize=6.8,
        fontname="helv",
        color=(0.45, 0.45, 0.45),
        align=fitz.TEXT_ALIGN_CENTER,
    )

    out = doc.tobytes(deflate=True, garbage=3, clean=True)
    doc.close()
    return out
