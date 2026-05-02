"""Generación de PDF de recibo de abono (estilo panel Cherry / contraste llamativo)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _receipt_legal_contact_email() -> str:
    return (os.getenv("RECEIPT_LEGAL_CONTACT_EMAIL") or "rockcity72@gmail.com").strip()


def _receipt_legal_contact_phone() -> str:
    return (os.getenv("RECEIPT_LEGAL_CONTACT_PHONE") or "3112157817").strip()


# Texto contractual del recibo (condiciones de cita, abonos y garantías).
_RECEIPT_LEGAL_BODY_TEMPLATE = """ATENCIÓN: SI NO PUEDE ASISTIR A LA CITA, LLÁMENOS CON HORAS DE
ANTICIPACIÓN. NUESTRO TIEMPO VALE TANTO COMO EL SUYO.
NO HAY DEVOLUCIONES DE DINERO POR ABONOS DE CITAS CANCELADAS.
PARA TATUAJES Y/O PERFORACIONES, ESTIMADO CLIENTE TENGA EN CUENTA LAS SIGUIENTES
RECOMENDACIONES:
* NO HAY DEVOLUCIONES DE DINERO DE ABONOS DE CITAS CANCELADAS.
* DESPUÉS DE CANCELAR SU CITA DOS VECES PERDERÁ EL VALOR ABONADO.
* TODO ABONO ES INTRANSFERIBLE.
* PARA MENORES DE EDAD, PRESENTARSE CON SU ACUDIENTE ÚNICAMENTE, PADRE Y/O MADRE, CON
ORIGINAL Y COPIA DE LOS DOCUMENTOS DE IDENTIFICACIÓN.
* EL PLAZO MÁXIMO PARA REALIZAR UN TATUAJE Y/O PERFORACIÓN ES DE 60 DÍAS CALENDARIO.
* PARA CUALQUIER CAMBIO O RECLAMO DEBE PRESENTAR ESTE DOCUMENTO.
* LA GARANTÍA DE SU TATUAJE, SERÁ CUBIERTA HASTA UN MES CALENDARIO, DESPUÉS DE REALIZADO
EL MISMO, PASADO ESTE TIEMPO, USTED PERDERÁ LA GARANTÍA EN MENCIÓN.
* LA GARANTÍA CUBRE POR FALTA DE RELLENO Y LÍNEAS INCOMPLETAS, MAS NO POR DESCUIDO O
INCUMPLIMIENTO EN LA FORMA DE CUIDARLO, RECUERDE QUE ESTE ES UN TRABAJO ARTESANAL.
* USTED SERÁ, CONTACTADO UN DÍA ANTES DE SU TATUAJE, POR VÍA TELEFÓNICA, WHATSAPP,
CORREO ELECTRÓNICO Y/O MENSAJE DE VOZ, (ESTOS TRES ÚLTIMOS SI USTED NO RESPONDE
NUESTRA LLAMADA), EN ELLOS SE DEJARA UN MENSAJE, INFORMÁNDOLE HASTA QUE HORA TIENE
USTED PLAZO DE COMUNICARSE CON NOSOTROS PARA CONFIRMAR O CANCELAR SU CITA, SI USTED
NO SE COMUNICA, DAMOS POR ENTENDIDO QUE NO PUEDE ASISTIR, Y SU CITA SERA CANCELADA.
* SI USTED CONFIRMA LA CITA PARA ASISTIR A SU TATUAJE Y NO ASISTE, PERDERÁ EL VALOR
ABONADO.
* EL DÍA DE LA CITA, USTED TIENE UN PLAZO HASTA DE 20 MINUTOS DESPUÉS DE LA HORA
PROGRAMADA PARA ASISTIR A LA MISMA, DESPUÉS DE ESE TIEMPO SU CITA SERÁ CANCELADA.
* SI USTED POR ALGÚN MOTIVO CANCELA SU CITA, PARA ASIGNAR UNA NUEVA FECHA, DEBE REALIZAR
OTRO ABONO. (RECUERDE SU ABONO INICIAL ES VIGENTE)
* RECUERDE QUE LA IDEA PRINCIPAL, IMÁGENES DEL PROYECTO, FOTOGRAFÍAS, CAMBIOS EN DISEÑO,
Y/O FORMA, DEBEN SER ENVIADAS POR LO MENOS UN DIA ANTERIOR A SU CITA, AL CORREO
ELECTRÓNICO {email} Y RECONFIRMANDO SU ENVÍO AL NÚMERO TELEFÓNICO {phone}"""


def _safe_paragraph_xml(text: str) -> str:
    """Escapa caracteres XML para usar el texto literal en un Paragraph de ReportLab."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _receipt_legal_flow_blocks() -> list[str]:
    """
    Agrupa el cuerpo legal en bloques que fluyen al ancho de página (sin <br/> por cada
    línea del fuente). Así la justificación reparte el espacio entre palabras de forma uniforme.
    """
    body = _RECEIPT_LEGAL_BODY_TEMPLATE.format(
        email=_receipt_legal_contact_email(),
        phone=_receipt_legal_contact_phone(),
    )
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    blocks: list[str] = []
    buf: list[str] = []
    for line in lines:
        if line.startswith("*"):
            if buf:
                blocks.append(" ".join(buf))
                buf = []
            buf.append(line)
        else:
            buf.append(line)
    if buf:
        blocks.append(" ".join(buf))
    return blocks


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_receipt_logo_path() -> Optional[str]:
    env = (os.getenv("RECEIPT_LOGO_PATH") or "").strip()
    if env and Path(env).is_file():
        return env
    root = _repo_root()
    for rel in ("streamlit_app/assets/branding.png", "assets/branding.png"):
        p = root / rel
        if p.is_file():
            return str(p)
    return None


def receipt_business_name() -> str:
    return (os.getenv("RECEIPT_BUSINESS_NAME") or "Cherry Tattoo").strip() or "Cherry Tattoo"


def receipt_business_address() -> str:
    return (os.getenv("RECEIPT_BUSINESS_ADDRESS") or "").strip()


def receipt_business_phone() -> str:
    return (os.getenv("RECEIPT_BUSINESS_PHONE") or "").strip()


def _fmt_cop(n: float) -> str:
    n = float(n)
    s = f"{n:,.2f}"
    return "$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def _scaled_logo_image(logo_path: str, max_w: float, max_h: float) -> Optional[Image]:
    """Escala el logo manteniendo proporción; nunca lo estira a un rectángulo fijo arbitrario."""
    try:
        ir = ImageReader(logo_path)
        iw, ih = ir.getSize()
        if iw <= 0 or ih <= 0:
            return None
        scale = min(max_w / float(iw), max_h / float(ih))
        return Image(logo_path, width=float(iw) * scale, height=float(ih) * scale)
    except Exception:
        return None


@dataclass
class PaymentReceiptPdfContext:
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


def build_payment_receipt_pdf(ctx: PaymentReceiptPdfContext) -> bytes:
    logo_path = resolve_receipt_logo_path()
    brand = receipt_business_name()
    addr = receipt_business_address()
    phone = receipt_business_phone()

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "hdr",
        parent=styles["Heading1"],
        fontSize=16,
        textColor=colors.HexColor("#ff2d6a"),
        spaceAfter=6,
        fontName="Helvetica-Bold",
    )
    sub_style = ParagraphStyle(
        "sub",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#4b5563"),
        spaceAfter=2,
    )
    body = ParagraphStyle(
        "body",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#111827"),
        leading=13,
    )
    legal_compact = ParagraphStyle(
        "legal_compact",
        parent=styles["Normal"],
        fontSize=7.5,
        textColor=colors.HexColor("#1f2937"),
        leading=10.2,
        alignment=TA_JUSTIFY,
        spaceBefore=0,
        spaceAfter=0,
    )
    accent_bg = colors.HexColor("#1a0a12")
    accent_soft = colors.HexColor("#fff0f5")

    logo_max_w = 40 * mm
    logo_max_h = 22 * mm
    logo_col_w = 44 * mm

    story: list = []

    left_header: list = [Paragraph(brand.upper(), title_style)]
    if addr:
        left_header.append(Paragraph(addr, sub_style))
    if phone:
        left_header.append(Paragraph(f"Tel. {phone}", sub_style))

    logo_img: Optional[Image] = None
    if logo_path:
        logo_img = _scaled_logo_image(logo_path, logo_max_w, logo_max_h)

    if logo_img is not None:
        text_col_w = max(doc.width - logo_col_w, 80 * mm)
        hdr = Table(
            [[left_header, [logo_img]]],
            colWidths=[text_col_w, logo_col_w],
        )
        hdr.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(hdr)
    else:
        for block in left_header:
            story.append(block)
    story.append(Spacer(1, 8))

    story.append(
        Paragraph(
            f"<b>RECIBO DE PAGO</b> — {ctx.kind_label}<br/>"
            f"<font size=9 color='#666666'>Emitido: {ctx.issued_at.strftime('%d/%m/%Y %H:%M')}</font>",
            body,
        )
    )
    story.append(Spacer(1, 10))

    note_row: tuple[str, str] | None
    if ctx.payment_note and str(ctx.payment_note).strip():
        note_row = ("Nota del movimiento", str(ctx.payment_note).strip())
    else:
        note_row = None

    data = [
        ("Cliente", ctx.client_name),
        ("Celular / contacto", ctx.client_phone),
        ("Cita", ctx.appointment_when),
        ("Servicio", ctx.service),
        ("Diseño / detalle", (ctx.detail or "—")[:800]),
        ("Valor total del trabajo", _fmt_cop(ctx.total_amount)),
        ("Abono en este recibo", _fmt_cop(ctx.this_payment)),
        ("Total abonado a la fecha", _fmt_cop(ctx.deposit_total_after)),
        ("Saldo pendiente", _fmt_cop(ctx.pending_after)),
    ]
    if note_row:
        data.insert(-3, note_row)

    t = Table(
        [[Paragraph(f"<b>{k}</b>", body), Paragraph(str(v), body)] for k, v in data],
        colWidths=[52 * mm, doc.width - 52 * mm],
    )
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), accent_soft),
                ("BOX", (0, 0), (-1, -1), 0.8, accent_bg),
                ("LINEBELOW", (0, 0), (-1, -2), 0.3, colors.white),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 14))

    banner = Table(
        [
            [
                Paragraph(
                    "<b>Condiciones y políticas del estudio</b>",
                    ParagraphStyle("b", parent=body, textColor=colors.white),
                )
            ]
        ],
        colWidths=[doc.width],
    )
    banner.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), accent_bg),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(banner)
    story.append(Spacer(1, 6))
    for bi, block in enumerate(_receipt_legal_flow_blocks()):
        if bi:
            story.append(Spacer(1, 5))
        story.append(Paragraph(_safe_paragraph_xml(block), legal_compact))

    doc.build(story)
    return buf.getvalue()
