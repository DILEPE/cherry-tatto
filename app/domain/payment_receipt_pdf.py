"""PDF de recibo de abono: orden de trabajo maquetada en código, alineada al diseño Rock City.

El diseño se compone en A4 y al final se escala a una tira del área imprimible del rollo
térmico ESC/POS (80 mm de papel, 72 mm de impresión / 576 dots).

Personalización del rollo:
- PAYMENT_RECEIPT_PAGE_WIDTH_MM — ancho imprimible (por defecto 72). El papel es 80 mm.
- PAYMENT_RECEIPT_PAGE_HEIGHT_MM — alto fijo opcional en mm; si se omite, se calcula con el contenido.

Cabecera negra (datos comerciales + título de orden y fecha), bloque de formulario en gris oscuro con inputs blancos redondeados
y etiquetas dentro de cada campo, franja roja y condiciones legales debajo.

Personalización opcional vía entorno:
- PAYMENT_RECEIPT_LOGO_IMAGE — ruta a PNG del logo (centrado en cabecera). Si no hay archivo, se intenta `app/assets/receipt_rock_city_logo.png`.
- PAYMENT_RECEIPT_CONTACT_IMAGE — ruta a PNG del bloque comercial (izquierda). Si no hay archivo, se pinta texto en blanco en negrita.
- PAYMENT_RECEIPT_ADDR_LINE1, PAYMENT_RECEIPT_ADDR_LINE2 — dirección si no usas imagen de contacto.
- PAYMENT_RECEIPT_CONTACT_LINE — línea opcional al pie (además de la fecha de generación).
- PAYMENT_RECEIPT_TERMS_EMAIL, PAYMENT_RECEIPT_TERMS_PHONE — correo y teléfono del párrafo final de envío de diseños.
- PAYMENT_RECEIPT_LOGO_LINE1, PAYMENT_RECEIPT_LOGO_LINE2, PAYMENT_RECEIPT_LOGO_MARK — solo si **no** hay PNG de logo (texto de respaldo).
"""
from __future__ import annotations

import html
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
PAYMENT_RECEIPT_SEND_FILENAME = "ORDEN DE TRABAJO.pdf"


def _mm_to_pt(mm: float) -> float:
    return float(mm) * 72.0 / 25.4


# Lienzo nativo del rollo (72 mm). Antes se dibujaba en A4 y al escalar la letra quedaba ilegible.
PAGE_W = _mm_to_pt(72)
PAGE_H = _mm_to_pt(210)


def _receipt_roll_width_mm() -> float:
    """Ancho imprimible. Impresora 80 mm ESC/POS: 72 mm (576 dots/línea)."""
    raw = (os.getenv("PAYMENT_RECEIPT_PAGE_WIDTH_MM") or "72").strip().replace(",", ".")
    try:
        value = float(raw)
    except ValueError:
        value = 72.0
    return min(max(value, 50.0), 216.0)


def _receipt_roll_height_mm() -> float | None:
    raw = (os.getenv("PAYMENT_RECEIPT_PAGE_HEIGHT_MM") or "").strip().replace(",", ".")
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return min(max(value, 80.0), 500.0)


def _page_used_height(page: fitz.Page) -> float:
    """Altura real del contenido (sin el vacío inferior del A4)."""
    bottom = 0.0
    for block in page.get_text("blocks"):
        bottom = max(bottom, float(block[3]))
    try:
        for drawing in page.get_drawings():
            rect = drawing.get("rect")
            if rect is not None:
                bottom = max(bottom, float(rect.y1))
    except (RuntimeError, ValueError, AttributeError):
        pass
    if bottom < 48.0:
        return float(page.rect.height)
    return min(float(page.rect.height), bottom + 4.0)


def _page_width_mm(page: fitz.Page) -> float:
    return float(page.rect.width) * 25.4 / 72.0


def ensure_thermal_receipt_pdf(pdf_bytes: bytes) -> bytes:
    """Reescala un PDF A4 (u otro tamaño) a la tira ESC/POS de 72 mm. Si ya lo es, no lo toca."""
    src = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        if src.page_count < 1:
            return pdf_bytes
        width_mm = _page_width_mm(src[0])
        target_mm = _receipt_roll_width_mm()
        if src.page_count == 1 and abs(width_mm - target_mm) <= 2.5:
            roll = _trim_roll_to_content(src)
        else:
            roll = _flatten_receipt_to_thermal_roll(src)
        out = roll.tobytes(deflate=True, garbage=3, clean=True)
        roll.close()
        return out
    finally:
        src.close()


def receipt_pdf_to_png(pdf_bytes: bytes, *, dpi: int = 203) -> bytes:
    """PNG monocromo a 203 dpi (576 px en 72 mm), recortado al contenido para el corte."""
    thermal = ensure_thermal_receipt_pdf(pdf_bytes)
    doc = fitz.open(stream=thermal, filetype="pdf")
    try:
        page = doc[0]
        pix = page.get_pixmap(dpi=max(int(dpi), 72), colorspace=fitz.csGRAY, alpha=False)
        pix = _thermalize_pixmap(pix, dpi=max(int(dpi), 72))
        return pix.tobytes("png")
    finally:
        doc.close()


def receipt_pdf_to_escpos(pdf_bytes: bytes, *, dpi: int = 203) -> bytes:
    """Ticket ESC/POS: raster 576 dots + avance corto + corte (GS V)."""
    png = receipt_pdf_to_png(pdf_bytes, dpi=dpi)
    pix = fitz.Pixmap(png)
    try:
        return _pixmap_to_escpos(pix)
    finally:
        del pix


def _pixmap_to_escpos(pix: fitz.Pixmap) -> bytes:
    if pix.alpha:
        pix = fitz.Pixmap(pix, 0)
    if pix.n != 1:
        pix = fitz.Pixmap(fitz.csGRAY, pix)
    width, height, stride = pix.width, pix.height, pix.stride
    samples = pix.samples
    width_bytes = (width + 7) // 8
    out = bytearray()
    out += b"\x1b\x40"  # ESC @ init
    out += b"\x1b\x33\x00"  # ESC 3 0 — interlineado 0
    max_band = 1600
    y0 = 0
    while y0 < height:
        band_h = min(max_band, height - y0)
        out += bytes(
            [
                0x1D,
                0x76,
                0x30,
                0x00,
                width_bytes & 0xFF,
                (width_bytes >> 8) & 0xFF,
                band_h & 0xFF,
                (band_h >> 8) & 0xFF,
            ]
        )
        for y in range(y0, y0 + band_h):
            row = y * stride
            for xb in range(width_bytes):
                byte = 0
                for bit in range(8):
                    x = xb * 8 + bit
                    if x < width and samples[row + x] < 128:
                        byte |= 0x80 >> bit
                out.append(byte)
        y0 += band_h
    # ~4 mm y corte completo: la térmica corta aquí, no al final de una hoja A4.
    out += b"\x1b\x4a\x28"  # ESC J n (avance en puntos)
    out += b"\x1d\x56\x00"  # GS V 0 full cut
    return bytes(out)


def _thermalize_pixmap(pix: fitz.Pixmap, *, dpi: int) -> fitz.Pixmap:
    """Negro sólido y recorte del blanco inferior para que el cutter actúe al final.

    En filas oscuras (cabecera / franja roja) se conserva el texto blanco: un umbral
    único de 230 se comía esas letras al binarizar el antialias. En filas claras se
    mantiene el umbral alto para que el trazo negro salga más denso.
    """
    if pix.alpha:
        pix = fitz.Pixmap(pix, 0)
    if pix.n != 1:
        pix = fitz.Pixmap(fitz.csGRAY, pix)
    width, height, stride = pix.width, pix.height, pix.stride
    samples = pix.samples_mv
    dark_row = bytearray(height)
    for y in range(height):
        row = y * stride
        acc = 0
        for x in range(width):
            acc += samples[row + x]
        dark_row[y] = 1 if (acc / float(width)) < 140 else 0
    min_ink = max(10, width // 64)
    last_ink = 0
    for y in range(height):
        row = y * stride
        ink_pixels = 0
        threshold = 128 if dark_row[y] else 230
        for x in range(width):
            idx = row + x
            if samples[idx] < threshold:
                samples[idx] = 0
                ink_pixels += 1
            else:
                samples[idx] = 255
        if ink_pixels >= min_ink:
            last_ink = y
    # 2 mm tras la última letra: el cutter de ESC/POS corta al terminar la página.
    pad = max(8, int(round(2.0 * float(dpi) / 25.4)))
    new_h = min(height, last_ink + 1 + pad)
    if new_h >= height:
        return pix
    cropped = fitz.Pixmap(fitz.csGRAY, fitz.IRect(0, 0, width, new_h), 0)
    dst = cropped.samples_mv
    dst_stride = cropped.stride
    for y in range(new_h):
        dst[y * dst_stride : y * dst_stride + width] = samples[y * stride : y * stride + width]
    return cropped


def _trim_roll_to_content(src: fitz.Document) -> fitz.Document:
    """Corta la página térmica justo después del último texto, para el auto-cutter."""
    page = src[0]
    used = _page_used_height(page)
    height = min(float(page.rect.height), used + _mm_to_pt(2.0))
    dest = fitz.open()
    out = dest.new_page(width=page.rect.width, height=height)
    out.show_pdf_page(
        out.rect,
        src,
        0,
        clip=fitz.Rect(0, 0, page.rect.width, height),
        keep_proportion=True,
    )
    return dest


def _flatten_receipt_to_thermal_roll(src: fitz.Document) -> fitz.Document:
    """Apila las páginas A4 en una sola tira del área imprimible (72 mm en rollo de 80 mm)."""
    out_w = _mm_to_pt(_receipt_roll_width_mm())
    cutter_pad = _mm_to_pt(2.0)
    clips: list[fitz.Rect] = []
    page_heights: list[float] = []
    for i in range(src.page_count):
        sp = src[i]
        clip = fitz.Rect(0, 0, sp.rect.width, _page_used_height(sp))
        clips.append(clip)
        scale = out_w / clip.width if clip.width else 1.0
        page_heights.append(clip.height * scale)
    content_h = sum(page_heights)
    forced_mm = _receipt_roll_height_mm()
    max_h = _mm_to_pt(min(forced_mm if forced_mm is not None else 200.0, 200.0))
    cutter_pad = min(cutter_pad, _mm_to_pt(1.5))
    out_h = min(content_h + cutter_pad, max_h)
    fit = 1.0
    usable = max(out_h - cutter_pad, _mm_to_pt(40.0))
    if content_h > usable > 0:
        fit = usable / content_h
        out_h = min(content_h * fit + cutter_pad, max_h)

    dest = fitz.open()
    page = dest.new_page(width=out_w, height=out_h)
    y = 0.0
    for i, src_h in enumerate(page_heights):
        h = src_h * fit
        page.show_pdf_page(
            fitz.Rect(0, y, out_w, y + h),
            src,
            i,
            clip=clips[i],
            keep_proportion=True,
        )
        y += h
    trimmed = _trim_roll_to_content(dest)
    dest.close()
    return trimmed

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

# Franja destacada: primer aviso de la lámina (el resto va como texto legal debajo).
_BANNER_NO_REFUND = "NO HAY DEVOLUCIONES DE DINERO DE ABONOS DE CITAS CANCELADAS"

_TERMS_LINES: tuple[str, ...] = (
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
    return _strip_env_value(os.getenv("PAYMENT_RECEIPT_TERMS_EMAIL") or "rockcity72@gmail.com")


def _terms_contact_phone() -> str:
    return _strip_env_value(os.getenv("PAYMENT_RECEIPT_TERMS_PHONE") or "WhatsApp: 3178000000")


def _strip_env_value(raw: str) -> str:
    t = (raw or "").strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "'\"":
        t = t[1:-1].strip()
    return t


def _addr_lines() -> tuple[str, str]:
    a1 = _strip_env_value(os.getenv("PAYMENT_RECEIPT_ADDR_LINE1") or "CRA 34 # 51 - 56")
    a2 = _strip_env_value(os.getenv("PAYMENT_RECEIPT_ADDR_LINE2") or "BUCARAMANGA - COLOMBIA")
    return a1, a2


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
    """Primera ruta existente: env → app/assets."""
    raw = (os.getenv("PAYMENT_RECEIPT_LOGO_IMAGE") or "").strip()
    candidates: list[Path] = []
    if raw:
        candidates.append(Path(raw))
    ad = _assets_dir()
    candidates.extend(
        [
            ad / "receipt_rock_city_logo.png",
            ad / "receipt_logo.png",
            ad / "rock_city_watermark.png",
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


def _insert_receipt_header_logo(page: fitz.Page, rect: fitz.Rect, path: str) -> bool:
    """Logo ROCK CITY recortado (sin el sello chino) para que quepa junto a la dirección."""
    try:
        pix = fitz.Pixmap(path)
        if pix.alpha:
            pix = fitz.Pixmap(pix, 0)
        top_h = max(1, int(pix.height * 0.72))
        clipped = fitz.Pixmap(pix, fitz.IRect(0, 0, pix.width, top_h))
        page.insert_image(rect, pixmap=clipped, keep_proportion=True)
        return True
    except (RuntimeError, ValueError, AttributeError, TypeError):
        return _insert_image_cover(page, rect, path)


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
    placeholder_if_empty: str = "-",
) -> None:
    """Campo blanco redondeado con la etiqueta dentro a la izquierda y el valor a la derecha."""
    _draw_round_rect(page, rect, radius_pct=radius_pct, fill=_WHITE, stroke=_BOX_EDGE, width=0.28)
    pad_x, pad_y = 4.0, 2.0
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
    shown = (value or "").strip()
    if not shown and placeholder_if_empty:
        shown = placeholder_if_empty
    if shown:
        _textbox_shrink_to_fit(
            page,
            rv,
            shown,
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
    """Tope vertical de la única hoja (deja margen para que no salte a una segunda)."""
    return PAGE_H - 4


def _contact_box_h() -> float:
    return 30.0


def _terms_body_limit() -> float:
    """El texto legal no invade la franja del correo/WhatsApp."""
    return _terms_page_bottom() - _contact_box_h()


def _emit_terms_paragraph(
    doc: fitz.Document,
    page: fitz.Page,
    y: float,
    mx: float,
    body: str,
    *,
    bullet: bool,
    color: tuple[float, float, float],
    fontsize: float = 5.25,
    gap_after: float = 0.75,
) -> tuple[fitz.Page, float]:
    """Pinta un párrafo (opcional «- ») en negrita para que el trazo se lea en térmica."""
    x0 = mx + 2
    x1 = PAGE_W - mx - 2
    full = f"- {body}" if bullet else body
    limit_y = _terms_body_limit()
    if y >= limit_y - 6:
        return page, y
    avail = max(limit_y - y - 1, 10.0)
    rect_h = min(120.0, avail)
    r = fitz.Rect(x0, y, x1, y + rect_h)
    fs = fontsize
    min_fs = 4.7
    rv = -1.0
    while fs >= min_fs:
        rv = page.insert_textbox(
            r,
            full,
            fontsize=fs,
            fontname="hebo",
            color=color,
            align=fitz.TEXT_ALIGN_LEFT,
        )
        if rv >= 0:
            advance = rect_h - rv
            return page, y + max(advance, fs * 1.12) + gap_after
        fs -= 0.25
    page.insert_textbox(
        r,
        full,
        fontsize=min_fs,
        fontname="hebo",
        color=color,
        align=fitz.TEXT_ALIGN_LEFT,
    )
    return page, min(y + min(rect_h, fs * 6.0) + gap_after, limit_y)


def _contact_email_phone() -> tuple[str, str]:
    email = _terms_contact_email()
    phone = _terms_contact_phone()
    if phone and not phone.upper().startswith("WHATSAPP"):
        phone = f"WhatsApp: {phone}"
    return email, phone


def _wrap_line(text: str, *, fs: float, max_w: float) -> list[str]:
    words = (text or "").split()
    if not words:
        return []
    lines: list[str] = []
    cur = words[0]
    for word in words[1:]:
        trial = f"{cur} {word}"
        if fitz.get_text_length(trial, fontname="hebo", fontsize=fs) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    lines.append(cur)
    return lines


def _ensure_contact_on_page(page: fitz.Page, mx: float) -> None:
    """Pinta correo y WhatsApp al final, siempre, si aún no están en la hoja."""
    email, phone = _contact_email_phone()
    existing = _norm_term_line(page.get_text() or "")
    email_key = _norm_term_line(email.split("@")[0] if email else "")
    if email_key and email_key in existing and "RECONFIRMANDO SU ENVIO" in existing:
        return
    fs = 5.6
    leading = 7.2
    max_w = PAGE_W - 2 * mx - 4
    lines = [email] if email else []
    lines.extend(_wrap_line(_POLICY_DESIGN_MIDDLE.strip(), fs=fs, max_w=max_w))
    if phone:
        lines.append(phone)
    lines = [ln for ln in lines if ln]
    need = leading * len(lines) + 3
    bottom_used = 0.0
    for block in page.get_text("blocks"):
        if isinstance(block[4], str) and block[4].strip():
            bottom_used = max(bottom_used, float(block[3]))
    y = bottom_used + 2.0
    if y + need > PAGE_H - 3:
        y = max(10.0, PAGE_H - 3 - need)
    x = mx + 2
    for line in lines:
        y += leading
        if y > PAGE_H - 1:
            break
        page.insert_text(fitz.Point(x, y), line, fontsize=fs, fontname="hebo", color=_INK)


def _text_has_receipt_contact(text: str) -> bool:
    n = _norm_term_line(text)
    email = _norm_term_line(_terms_contact_email())
    return bool(email and email in n) or "RECONFIRMANDO SU ENVIO" in n


def _is_contact_only_line(text: str) -> bool:
    n = _norm_term_line(text)
    email = _norm_term_line(_terms_contact_email())
    if email and (n == email or n.startswith(email)):
        return True
    if n.startswith("Y RECONFIRMANDO"):
        return True
    if n.startswith("WHATSAPP"):
        return True
    return False


def _emit_design_delivery_paragraph(
    doc: fitz.Document,
    page: fitz.Page,
    y: float,
    mx: float,
) -> tuple[fitz.Page, float]:
    """Aviso de envío de diseño; el correo y WhatsApp se pintan al final de la hoja."""
    return _emit_terms_paragraph(
        doc, page, y, mx, _POLICY_DESIGN_PREFIX.strip(), bullet=False, color=_INK
    )


def _norm_term_line(text: str) -> str:
    t = " ".join((text or "").upper().replace(".", " ").replace("-", " ").split())
    return t


def _is_banner_no_refund_line(text: str) -> bool:
    """True si el párrafo es el aviso de no devolución (ya va en la franja)."""
    banner = _norm_term_line(_BANNER_NO_REFUND)
    candidate = _norm_term_line(text)
    return candidate == banner or candidate.startswith(banner)


def _render_terms_blocks(doc: fitz.Document, page: fitz.Page, y: float, mx: float) -> tuple[fitz.Page, float]:
    """Condiciones generales + política de confirmación/cita (varias páginas si hace falta)."""
    for line in _TERMS_LINES:
        if _is_banner_no_refund_line(line):
            continue
        page, y = _emit_terms_paragraph(doc, page, y, mx, line, bullet=True, color=_INK)
    y += 1
    for body, bullet, col in _POLICY_CONFIRMATION:
        page, y = _emit_terms_paragraph(doc, page, y, mx, body, bullet=bullet, color=col)
    return _emit_design_delivery_paragraph(doc, page, y, mx)


def _html_to_term_blocks(raw_html: str) -> list[tuple[str, bool]]:
    """Convierte HTML de plantilla recibo a párrafos (texto, es_viñeta) para la zona legal del PDF."""
    from html.parser import HTMLParser

    class _Parser(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.blocks: list[tuple[str, bool]] = []
            self._buf: list[str] = []
            self._in_li = False
            self._skip = 0

        def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
            t = tag.lower()
            if t in ("script", "style"):
                self._skip += 1
                return
            if self._skip:
                return
            if t == "li":
                self._flush(False)
                self._in_li = True
            elif t in ("p", "div", "h1", "h2", "h3", "h4", "tr", "br"):
                if t == "br":
                    self._buf.append("\n")
                else:
                    self._flush(False)

        def handle_endtag(self, tag: str) -> None:
            t = tag.lower()
            if t in ("script", "style") and self._skip:
                self._skip -= 1
                return
            if self._skip:
                return
            if t == "li":
                self._flush(True)
                self._in_li = False
            elif t in ("p", "div", "h1", "h2", "h3", "h4", "tr"):
                self._flush(False)

        def handle_data(self, data: str) -> None:
            if self._skip:
                return
            if data:
                self._buf.append(data)

        def _flush(self, as_bullet: bool) -> None:
            text = " ".join("".join(self._buf).split())
            self._buf = []
            if text:
                self.blocks.append((text, as_bullet or self._in_li))

        def close(self) -> None:
            self._flush(False)
            super().close()

    src = (raw_html or "").strip()
    if not src:
        return []
    parser = _Parser()
    try:
        parser.feed(src)
        parser.close()
    except Exception:
        plain = re.sub(r"<[^>]+>", " ", src)
        plain = " ".join(html.unescape(plain).split())
        return [(plain, False)] if plain else []
    if parser.blocks:
        return parser.blocks
    plain = re.sub(r"<[^>]+>", " ", src)
    plain = " ".join(html.unescape(plain).split())
    return [(plain, False)] if plain else []


def _render_contract_html_as_terms(
    doc: fitz.Document,
    page: fitz.Page,
    y: float,
    mx: float,
    contract_html: str,
) -> tuple[fitz.Page, float]:
    """Pinta el contenido de la plantilla recibo en la zona de condiciones (mismo layout tipográfico)."""
    blocks = _html_to_term_blocks(contract_html)
    if not blocks:
        return _render_terms_blocks(doc, page, y, mx)
    has_prefix = any("RECUERDE QUE LA IDEA" in _norm_term_line(t) for t, _ in blocks)
    for text, bullet in blocks:
        if _is_banner_no_refund_line(text) or _is_contact_only_line(text):
            continue
        page, y = _emit_terms_paragraph(doc, page, y, mx, text, bullet=bullet, color=_INK)
    if not has_prefix:
        page, y = _emit_terms_paragraph(
            doc, page, y, mx, _POLICY_DESIGN_PREFIX.strip(), bullet=False, color=_INK
        )
    return page, y


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
    # HTML de plantilla activa `recibo` (placeholders ya sustituidos). Se pinta bajo la franja ATENCIÓN.
    contract_html: Optional[str] = None
    # False: oculta las cajas PRECIO / ABONO 1–3 (orden sin importes).
    include_abono_amounts: bool = True


def build_payment_receipt_pdf(ctx: PaymentReceiptPdfContext) -> bytes:
    global PAGE_W, PAGE_H
    PAGE_W = _mm_to_pt(_receipt_roll_width_mm())
    PAGE_H = _mm_to_pt(200.0)

    doc = fitz.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)

    mx = 6.0
    inner_w = PAGE_W - 2 * mx
    header_h = 44.0
    gray_pad_v = 3.0
    row_h = 15.5
    row_gap = 1.8
    dis_h = 20.0
    gap_mid = 3.5
    banner_h = 18.0
    fs_lab, fs_val = 7.6, 8.8

    show_amounts = bool(ctx.include_abono_amounts)
    y = header_h + gray_pad_v
    y_nom = y
    y_ch = y_nom + row_h + row_gap
    y_em = y_ch + row_h + row_gap
    y_dis = y_em + row_h + row_gap
    y_pay = y_dis + dis_h + row_gap
    if show_amounts:
        form_bottom = y_pay + row_h + row_gap + row_h + gray_pad_v
    else:
        form_bottom = y_dis + dis_h + gray_pad_v

    page.draw_rect(fitz.Rect(0, header_h, PAGE_W, form_bottom), color=_FORM_GRAY, fill=_FORM_GRAY, width=0)
    page.draw_rect(fitz.Rect(0, 0, PAGE_W, header_h), color=_BLACK, fill=_BLACK, width=0)

    a1, a2 = _addr_lines()
    d_str, m_str, y_str = _issued_dma(ctx.issued_at)
    logo_w = 78.0
    logo_rect = fitz.Rect(PAGE_W - mx - logo_w, 1.5, PAGE_W - mx, 30.0)
    logo_png = resolve_payment_receipt_logo_png()
    if not logo_png or not _insert_receipt_header_logo(page, logo_rect, logo_png):
        logo1, logo2 = _logo_lines()
        page.insert_textbox(
            logo_rect,
            f"{logo1.upper()}\n{logo2.upper()}",
            fontsize=8.0,
            fontname="hebo",
            color=_WHITE,
            align=fitz.TEXT_ALIGN_CENTER,
        )
    addr_x1 = mx
    addr_x2 = max(mx + 70.0, PAGE_W - mx - logo_w - 3.0)
    addr_block = f"{a1.upper()}\n{a2.upper()}"
    _textbox_shrink_to_fit(
        page,
        fitz.Rect(addr_x1, 4.0, addr_x2, 30.5),
        addr_block,
        fontsize=7.2,
        fontname="hebo",
        color=_WHITE,
        align=fitz.TEXT_ALIGN_LEFT,
        min_fs=5.4,
    )
    page.insert_textbox(
        fitz.Rect(mx, 31.0, PAGE_W - mx, 43.0),
        f"FECHA  ·  {d_str}/{m_str}/{y_str}",
        fontsize=7.0,
        fontname="hebo",
        color=_WHITE,
        align=fitz.TEXT_ALIGN_CENTER,
    )

    cita_str, hora_str = _appointment_cita_y_hora(ctx.appointment_when)
    half = (inner_w - gap_mid) / 2
    _field_inline(
        page, fitz.Rect(mx, y_nom, mx + half * 1.15, y_nom + row_h),
        "NOMBRE:", ctx.client_name or "-", label_width=46.0, fs_label=fs_lab, fs_val=8.4, radius_pct=0.4,
    )
    _field_inline(
        page, fitz.Rect(mx + half * 1.15 + gap_mid, y_nom, PAGE_W - mx, y_nom + row_h),
        "CEL:", ctx.client_phone or "-", label_width=26.0, fs_label=fs_lab, fs_val=8.4, radius_pct=0.4,
    )
    _field_inline(
        page, fitz.Rect(mx, y_ch, mx + half, y_ch + row_h),
        "CITA:", cita_str or "-", label_width=34.0, fs_label=fs_lab, fs_val=9.2, radius_pct=0.4,
    )
    _field_inline(
        page, fitz.Rect(mx + half + gap_mid, y_ch, PAGE_W - mx, y_ch + row_h),
        "HORA:", hora_str or "-", label_width=36.0, fs_label=fs_lab, fs_val=9.2, radius_pct=0.4,
    )
    _field_inline(
        page, fitz.Rect(mx, y_em, PAGE_W - mx, y_em + row_h),
        "E-MAIL:", ctx.client_email or "-", label_width=46.0, fs_label=fs_lab, fs_val=8.6, radius_pct=0.4,
    )

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
        fitz.Rect(mx, y_dis, PAGE_W - mx, y_dis + dis_h),
        "DISEÑO:",
        diseno_txt,
        label_width=50.0,
        fs_label=fs_lab,
        fs_val=8.6,
        radius_pct=0.28,
    )

    if show_amounts:
        amounts = [float(a) for a, _ in ctx.payment_history]
        if not amounts and float(ctx.this_payment or 0) > 0:
            amounts = [float(ctx.this_payment)]
        a1s, a2s, a3s = _split_abono_amounts_for_boxes(amounts)
        _field_inline(
            page, fitz.Rect(mx, y_pay, PAGE_W - mx, y_pay + row_h),
            "PRECIO $", _fmt_cop(ctx.total_amount),
            label_width=58.0, fs_label=fs_lab, fs_val=10.2, val_bold=True, radius_pct=0.4,
        )
        y_ab = y_pay + row_h + row_gap
        _field_inline(
            page, fitz.Rect(mx, y_ab, mx + half, y_ab + row_h),
            "ABONO 1", _fmt_money_cell(a1s),
            label_width=48.0, fs_label=7.8, fs_val=8.8, radius_pct=0.4,
        )
        _field_inline(
            page, fitz.Rect(mx + half + gap_mid, y_ab, PAGE_W - mx, y_ab + row_h),
            "ABONO 2", _fmt_money_cell(a2s),
            label_width=48.0, fs_label=7.8, fs_val=8.8, radius_pct=0.4,
        )
    banner_y0 = form_bottom
    page.draw_rect(fitz.Rect(0, banner_y0, PAGE_W, banner_y0 + banner_h), color=_RED_STRIP, fill=_RED_STRIP, width=0)
    _textbox_shrink_to_fit(
        page,
        fitz.Rect(mx, banner_y0 + 2, PAGE_W - mx, banner_y0 + banner_h - 2),
        _BANNER_NO_REFUND,
        fontsize=6.8,
        fontname="hebo",
        color=_WHITE,
        align=fitz.TEXT_ALIGN_CENTER,
        min_fs=5.2,
        step=0.25,
    )

    body_top = banner_y0 + banner_h + 2.5
    contract_src = (ctx.contract_html or "").strip()
    if contract_src:
        _render_contract_html_as_terms(doc, page, body_top, mx, contract_src)
    else:
        _render_terms_blocks(doc, page, body_top, mx)
    _ensure_contact_on_page(page, mx)

    roll = _flatten_receipt_to_thermal_roll(doc)
    out = roll.tobytes(deflate=True, garbage=3, clean=True)
    roll.close()
    doc.close()
    return out
