#!/usr/bin/env python3
"""
Genera PDF del manual de usuario del panel, uno por rol (administrador, vendedor, perforador, tatuador).

Requisitos: PyMuPDF (pymupdf), ya listado en requirements.txt.

Uso (desde la raíz del repo):
  python scripts/build_manual_pdfs_by_role.py

Salida por defecto: docs/manual-por-rol/manual-panel-<rol>.pdf
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import fitz


_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_OUT = _ROOT / "docs" / "manual-por-rol"

_CSS = """
body { font-family: Helvetica, Arial, sans-serif; font-size: 11pt; line-height: 1.35; color: #222; }
h1 { font-size: 20pt; margin-bottom: 6pt; color: #111; }
h2 { font-size: 13pt; margin-top: 14pt; margin-bottom: 6pt; color: #333; }
p { margin: 6pt 0; }
ul { margin: 6pt 0 6pt 18pt; padding-left: 8pt; }
li { margin: 3pt 0; }
.small { font-size: 9pt; color: #555; margin-top: 18pt; }
"""


def _wrap(body: str, title: str) -> str:
    return f"""<html><head><meta charset="utf-8"/><style>{_CSS}</style></head><body>
<h1>{title}</h1>
{body}
<p class="small">Cherry Ink · Rock City — Panel operativo. Basado en la documentación interna del proyecto.</p>
</body></html>"""


def html_administrador() -> str:
    body = """
<h2>1. Tu perfil</h2>
<p>Eres <strong>Administrador</strong>: ves todos los módulos operativos (citas, clientes, contratos, encuestas, reporte) y además la pestaña <strong>Gestión de usuarios</strong>. Asignas qué módulos puede usar cada usuario que no sea administrador.</p>

<h2>2. Acceso al panel</h2>
<ul>
<li>Abre la URL del panel Streamlit (puerto habitual 8501).</li>
<li>La API debe estar activa (variable <code>API_BASE_URL</code> / puerto en <code>.env</code>).</li>
<li>Tras iniciar sesión: sidebar con selector de módulo, <strong>Probar conexión</strong>, <strong>Verificar n8n</strong>, <strong>Cerrar sesión</strong>.</li>
</ul>

<h2>3. Módulos que puedes delegar</h2>
<ul>
<li><strong>Gestión citas</strong>: calendario, filtros, agendar, ver día, firma, montos, reprogramar, recibos, anular.</li>
<li><strong>Gestión de clientes</strong>: fichas y validaciones de documento/contacto.</li>
<li><strong>Gestión contratos</strong>: plantillas HTML por tipo tatuaje/piercing y plantilla activa.</li>
<li><strong>Gestión encuesta</strong>: preguntas dinámicas (tipos, opciones, alcance tattoo/piercing/both).</li>
<li><strong>Reporte</strong>: Finanzas — citas y Encuestas — satisfacción.</li>
</ul>

<h2>4. Gestión de usuarios (exclusivo administrador)</h2>
<ul>
<li>Alta/edición de usuarios: nombre, usuario, contraseña, tienda, rol (administrador, vendedor, perforador, tatuador).</li>
<li><strong>Módulos permitidos</strong> (checkboxes) para quien no es administrador: citas, clientes, contratos, encuestas, reporte.</li>
<li>Si un usuario sin rol administrador no tiene ningún módulo marcado, verá un aviso al entrar.</li>
<li>Los administradores tienen acceso operativo completo sin depender de esos checkboxes.</li>
</ul>

<h2>5. Flujo de agendamiento (referencia para capacitar al equipo)</h2>
<ol>
<li>Gestión citas → filtros del calendario → día (solo desde hoy).</li>
<li>Diálogo Agendar cita: tipo tatuaje/piercing, duración en franjas de 30 min, profesional, hora libre, cliente (búsqueda por documento o alta), montos, notas/prioridad.</li>
<li>Tras guardar: la cita aparece en calendario y en “Ver citas del día”.</li>
<li>Desde la lista del día: Firmar contrato, Reprogramar, Montos, Recibos, Anular según reglas y estado.</li>
</ol>

<h2>6. Cita express (piercing)</h2>
<p>Botón junto a “Filtros del calendario”. Flujo: agenda con <strong>abono igual al valor total</strong> → datos completos del cliente (POST) → cita (POST) → continúa en firma digital en etapa de <strong>cuestionario</strong> y luego firma. Los tatuadores/perforadores no pueden iniciarlo desde ese botón.</p>

<h2>7. Firma digital de contrato</h2>
<p>Vista interna (no es pestaña del menú): datos personales → cuestionario según tipo → firma. Requiere cita con cliente, servicio que exija contrato y <strong>cobro completo</strong> para avanzar tras el cuestionario.</p>

<h2>8. Reportes y encuestas</h2>
<p><strong>Reporte → Finanzas</strong>: filtros, tabla/métricas, export Excel según implementación. <strong>Reporte → Encuestas</strong>: agregados por pregunta y gráficos cuando aplique.</p>

<h2>9. Integraciones</h2>
<p>n8n recibe webhooks (citas, recibos PDF, contrato firmado, consentimiento/cuidados por procedimiento, alertas de encuesta baja, etc.) según configuración del servidor API.</p>

<h2>10. Buenas prácticas</h2>
<ul>
<li>Mantén montos correctos antes de la firma.</li>
<li>Alinea preguntas de encuesta y etiquetas de procedimiento con los PDF cargados en base de datos para consentimientos piercing.</li>
<li>Principio de mínimo privilegio al asignar módulos.</li>
</ul>
"""
    return _wrap(body, "Manual de usuario — Administrador")


def html_vendedor() -> str:
    body = """
<h2>1. Tu perfil</h2>
<p>Eres <strong>Vendedor</strong> (u operativo similar). Lo que ves en el menú lateral depende de los <strong>módulos</strong> que un administrador te haya marcado en <strong>Gestión de usuarios</strong>. Este manual resume lo habitual si tienes citas, clientes y reportes.</p>

<h2>2. Acceso</h2>
<ul>
<li>URL del panel + API encendida.</li>
<li>Inicio de sesión con usuario y contraseña dados por administración.</li>
</ul>

<h2>3. Gestión citas (si tienes el módulo)</h2>
<ul>
<li><strong>Calendario</strong>: filtros por nombre, servicio, estado; filtro por profesional si tu perfil lo permite ver todas las citas.</li>
<li><strong>Agendar</strong>: elige día → tipo tatuaje o piercing → duración → profesional → hora → cliente y montos → guardar.</li>
<li><strong>Ver citas del día</strong>: desde el calendario puedes abrir acciones por cita: <strong>Firmar contrato</strong>, <strong>Reprogramar</strong>, <strong>Montos</strong>, <strong>Recibos</strong>, <strong>Anular</strong> (según estado).</li>
<li><strong>Cita express</strong> (piercing): botón junto a filtros; acelera agenda + alta cliente + cita y lleva al cuestionario/firma; exige saldo pagado al completo en ese paso.</li>
</ul>

<h2>4. Firma de contrato</h2>
<p>Desde “Firmar contrato”: completar datos del cliente si falta algo, encuesta según tipo de servicio, firma en lienzo. La cita debe estar <strong>totalmente abonada</strong> para cerrar el flujo.</p>

<h2>5. Gestión de clientes (si tienes el módulo)</h2>
<p>Búsqueda, alta y edición de fichas (documento, contacto, redes, emergencia, menores/tutor según reglas).</p>

<h2>6. Gestión contratos / Gestión encuesta (si te los asignan)</h2>
<ul>
<li><strong>Contratos</strong>: plantillas HTML por tipo y cuál está activa.</li>
<li><strong>Encuesta</strong>: preguntas que verán los usuarios en el paso previo a firmar (solo lectura operativa si no eres quien las configura).</li>
</ul>

<h2>7. Reporte (si tienes el módulo)</h2>
<ul>
<li><strong>Finanzas — citas</strong>: consultas y exportación para cuadrar montos.</li>
<li><strong>Encuestas — satisfacción</strong>: resultados agregados por pregunta.</li>
</ul>

<h2>8. Lo que no suele tocar el vendedor</h2>
<p>La pestaña <strong>Gestión de usuarios</strong> es solo para administradores. Si algo falla de permisos, pide al administrador que revise tus módulos permitidos.</p>
"""
    return _wrap(body, "Manual de usuario — Vendedor")


def html_perforador() -> str:
    body = """
<h2>1. Tu perfil</h2>
<p>Eres <strong>Perforador</strong>: tu trabajo en el panel suele centrarse en ver tu agenda y <strong>firmar contratos</strong> de tus citas piercing/tatuaje según corresponda al servicio. Los módulos extra (clientes, reportes…) solo aparecen si un administrador te los asignó.</p>

<h2>2. Acceso</h2>
<p>Misma URL y credenciales que el resto del equipo; API debe estar disponible.</p>

<h2>3. Gestión citas — lo que verás</h2>
<ul>
<li>Calendario <strong>filtrado</strong>: citas <strong>tuyas</strong>, estados activos (agendada/reprogramada) y <strong>fecha desde hoy</strong>.</li>
<li><strong>No puedes agendar</strong> haciendo clic en el día del calendario (botón deshabilitado para tu rol).</li>
<li><strong>Cita express</strong>: el botón junto a “Filtros del calendario” está <strong>deshabilitado</strong> para tatuadores y perforadores.</li>
<li>Abre <strong>Ver citas del día</strong> / lista del día: aquí tu acción principal es <strong>Firmar contrato</strong> cuando la cita y el pago lo permiten.</li>
<li>No verás desde esa vista las acciones de recepción (<strong>Reprogramar</strong>, <strong>Montos</strong>, <strong>Recibos</strong>, <strong>Anular</strong>) como los ve el personal de mostrador.</li>
</ul>

<h2>4. Firma digital de contrato</h2>
<p>Al pulsar <strong>Firmar contrato</strong> entras en la vista de tres etapas: datos del cliente → cuestionario → firma. Debes cumplir las mismas reglas de negocio (pago completo para completar firma, tipo de servicio que exija contrato, etc.).</p>

<h2>5. Otros módulos</h2>
<p>Si tienes <strong>Gestión de clientes</strong> o <strong>Reporte</strong> asignados, funcionan igual que para el resto de roles; lo habitual es que el perforador solo use <strong>citas</strong>.</p>

<h2>6. Si necesitas cambiar horarios o montos</h2>
<p>Pide a recepción/vendedor o administrador que use las acciones del día correspondientes.</p>
"""
    return _wrap(body, "Manual de usuario — Perforador")


def html_tatuador() -> str:
    body = """
<h2>1. Tu perfil</h2>
<p>Eres <strong>Tatuador</strong>: en el panel tu uso típico es consultar <strong>tu agenda</strong> y ejecutar el flujo de <strong>firma de contrato</strong> para citas de tatuaje asignadas a ti. El comportamiento del panel respecto a restricciones es el mismo que para el perforador, pero en el eje de agenda/servicios de <strong>tatuaje</strong>.</p>

<h2>2. Acceso</h2>
<p>Misma URL y credenciales; la API debe estar en línea.</p>

<h2>3. Gestión citas — restricciones de rol</h2>
<ul>
<li>Ves citas <strong>propias</strong>, <strong>activas</strong>, con fecha <strong>desde hoy</strong>.</li>
<li><strong>No agendamos</strong> desde el calendario con tu usuario.</li>
<li>El botón <strong>Cita express</strong> (piercing) está <strong>deshabilitado</strong> para tatuador/perforador en esa ubicación.</li>
<li>En la lista del día, usa <strong>Firmar contrato</strong> cuando corresponda.</li>
<li>Las gestiones de mostrador (reprogramar, montos, recibos, anular) las realiza personal con permisos.</li>
</ul>

<h2>4. Firma digital</h2>
<p>Vista en tres pasos: datos personales → encuesta según tipo tatuaje/piercing → firma en plantilla activa. Condiciones de pago y tipo de servicio las marca el sistema.</p>

<h2>5. Otros módulos</h2>
<p>Si administración te asignó clientes, contratos, encuestas o reportes, el comportamiento es el estándar del panel; lo habitual es operar solo en <strong>Gestión citas</strong>.</p>

<h2>6. Coordinación con recepción</h2>
<p>Para nuevas citas, cambios de hora o abonos, coordina con quien tenga el módulo de citas completo.</p>
"""
    return _wrap(body, "Manual de usuario — Tatuador")


ROLE_BUILDERS = {
    "administrador": html_administrador,
    "vendedor": html_vendedor,
    "perforador": html_perforador,
    "tatuador": html_tatuador,
}


def write_pdf_from_html(html: str, pdf_path: Path) -> None:
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    if pdf_path.exists():
        pdf_path.unlink()
    writer = fitz.DocumentWriter(str(pdf_path))
    mediabox = fitz.paper_rect("a4")
    where = mediabox + (36, 36, -36, -36)
    story = fitz.Story(html)
    while True:
        device = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(device)
        writer.end_page()
        if not more:
            break
    writer.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera PDF del manual por rol del panel.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=_DEFAULT_OUT,
        help=f"Carpeta de salida (por defecto: {_DEFAULT_OUT})",
    )
    parser.add_argument(
        "--roles",
        nargs="*",
        choices=sorted(ROLE_BUILDERS.keys()),
        help="Roles a generar (por defecto: todos)",
    )
    args = parser.parse_args()
    out_dir = Path(args.out_dir).resolve()
    roles = args.roles if args.roles else list(ROLE_BUILDERS.keys())

    for role in roles:
        html = ROLE_BUILDERS[role]()
        out_file = out_dir / f"manual-panel-{role}.pdf"
        write_pdf_from_html(html, out_file)
        print(f"[ok] {out_file.relative_to(_ROOT)}")

    print(f"Generados {len(roles)} PDF en: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
