# Manual de usuario — Panel Cherry Ink · Rock City

Documento orientado al **usuario del panel** (recepción, administración, ventas y profesionales). Describe el flujo general, los módulos, los roles y las funciones principales según la aplicación Streamlit que consume la API Litestar.

---

## 1. Acceso al panel

1. Abre la URL del panel Streamlit en el navegador (puerto habitual **8501**, según despliegue).
2. La API Litestar debe estar en ejecución en la dirección configurada en `.env` (`API_BASE_URL` / `PORT`), o el panel mostrará errores de conexión.
3. **Inicio de sesión**
   - **Modo base de datos** (`PANEL_AUTH_USERS_SOURCE=database` u opción equivalente): usuario y contraseña creados en **Gestión de usuarios** (solo administradores pueden dar de alta cuentas).
   - **Modo solo entorno / desarrollo**: puede existir acceso amplio sin permisos granulares (según `.env`).
4. Tras entrar, el sidebar muestra el **módulo activo** (radio) y acciones comunes: **Probar conexión**, **Verificar n8n**, **Cerrar sesión**.

---

## 2. Roles del panel

| Rol interno     | Etiqueta habitual | Uso general |
|-----------------|-------------------|-------------|
| `administrador` | Administrador     | Acceso a **todos** los módulos operativos y a **Gestión de usuarios**. Asigna permisos por módulo al resto de usuarios. |
| `vendedor`      | Vendedor          | Operación front-office: citas, clientes, reportes, etc., según módulos asignados. |
| `perforador`    | Perforador        | Profesional piercing; vista de agenda **acotada** (solo sus citas activas desde hoy). No agenda desde calendario ni usa **Cita express** desde ese botón. |
| `tatuador`      | Tatuador          | Igual que perforador pero para eje tatuaje. |

Los roles **no sustituyen** la matriz de **módulos permitidos**: un usuario que no sea administrador solo ve las pestañas que un administrador le haya marcado en **Gestión de usuarios → Editar → Módulos permitidos**. Si no tiene ninguno, el panel muestra un aviso para contactar al administrador.

---

## 3. Módulos del panel (qué es cada uno)

Los módulos **asignables** por administrador son:

| Clave interna | Nombre en pantalla      | Propósito |
|---------------|-------------------------|-----------|
| `citas`       | Gestión citas           | Calendario, filtros, agendar citas, ver día, firma de contrato, montos, reprogramación, recibos, anular. |
| `clientes`    | Gestión de clientes     | Alta, edición y búsqueda de fichas de cliente; vínculo con documentos y datos para contratos. |
| `contratos`   | Gestión contratos       | Administración de **plantillas HTML** de contrato por tipo (tatuaje / piercing): crear, editar, activar. |
| `encuestas`   | Gestión encuesta        | Configuración de **preguntas dinámicas** que verá el cliente/proceso de firma (tipos, opciones, alcance tattoo/piercing). |
| `reporte`     | Reporte                 | Subsecciones: **Finanzas — citas** y **Encuestas — satisfacción**. |

**Gestión de usuarios** (`usuarios_panel`): **solo administradores** (o sesión con acceso total según configuración). No es un módulo “asignable” en la lista anterior; aparece automáticamente para quien sea administrador operativo.

---

## 4. Flujo general desde el inicio hasta terminar un agendamiento

Escenario típico: **vendedor** o **administrador** con módulo **Gestión citas**.

1. **Abrir “Gestión citas”** en el sidebar.
2. **Revisar filtros del calendario** (nombre, servicio, estado) y, si aplica, filtro por profesional en la agenda.
3. **Elegir el día** en el calendario (solo fechas **desde hoy** permiten agendar).
4. Se abre el diálogo **“Agendar cita”**:
   - **Tipo de trabajo**: tatuaje o piercing (determina el profesional asignable y el eje de agenda).
   - **Duración en franjas** de 30 minutos (cuántos huecos consecutivos bloquea en la agenda).
   - **Profesional asignado**: tatuador o perforador según el tipo; si tu usuario es ese rol y no tienes acceso total, la cita puede quedar **autoasignada** a ti.
   - **Franja de inicio**: solo horarios libres según ocupación del día.
   - **Datos del cliente**: puede **buscar por documento** un cliente existente o dar de alta datos mínimos para crear uno nuevo en el mismo paso (según el formulario).
   - **Montos**: valor total, abono inicial; el sistema calcula saldo pendiente.
   - **Prioridad / notas** según formulario.
5. **Guardar**: la API crea la cita (y cliente si aplica). Según tipo de servicio y abono, puede generarse **recibo PDF** o solo notificación (piercing tiene reglas distintas para recibo inicial).
6. **Post-agendamiento**
   - La cita aparece en el calendario y en **“Ver citas del día”** si hay más detalle.
   - Desde la lista del día (usuarios no técnicos): **Firmar contrato**, **Reprogramar**, **Montos**, **Recibos**, **Anular** según estado y reglas de negocio.
   - **Firma de contrato**: requiere cita con cliente vinculado, servicio que exija contrato, y **cita totalmente abonada** para pasar del cuestionario a la firma final.

**Profesionales (tatuador / perforador)** con módulo citas: ven un calendario filtrado a **sus** citas **activas** desde hoy; desde **“Ver citas del día”** pueden usar sobre todo **Firmar contrato** (sin agendar ni montos desde ahí).

---

## 5. Cita express (piercing)

Objetivo: acelerar el flujo **piercing** cuando se quiere **agenda + ficha completa del cliente + encuesta + firma** en una sola sesión del panel.

1. En **Gestión citas**, junto al título **“Filtros del calendario”**, el botón **Cita express** (los roles **tatuador / perforador** lo tienen **deshabilitado** desde ahí).
2. Se abre una vista interna de firma (`express_piercing`) **sin** `appointment_id` todavía:
   - **Paso agenda**: fecha, perforador, duración en franjas, hora libre, notas, montos. Para poder llegar a encuesta y firma, el diseño exige **abono igual al valor total** (sin saldo pendiente).
   - **Paso datos personales**: misma exigencia de campos que la etapa 1 del flujo de firma (documento, contacto, redes, emergencia, etc.). Se crea el cliente por API (**POST**) y luego la cita (**POST**) vinculada a ese cliente.
3. Al terminar, el panel **salta** al flujo normal de **Firma digital de contrato** en la **etapa 2 (cuestionario)** y luego **etapa 3 (firma)**.
4. **Notificaciones / PDF**: siguen las reglas del backend (por ejemplo recibo inicial en piercing puede estar omitido según configuración).

---

## 6. Firma digital de contrato (vista aparte)

No es una pestaña del sidebar: se abre con botones **“Firmar contrato”** (navegación interna con parámetros `view=contract_sign&appointment_id=…`).

**Etapas habituales**

1. **Datos personales** del cliente (PUT cliente; validaciones de documento, teléfonos, etc.).
2. **Cuestionario** dinámico según tipo de contrato (preguntas configuradas en **Gestión encuesta** con alcance tattoo/piercing/both).
3. **Firma del contrato**: plantilla activa del tipo correspondiente, canvas de firmas, en menores datos de tutor si aplica; envío a API y cierre de flujo.

Condiciones resumidas: **pago completo** de la cita para firmar; servicios tipo **cambio/limpieza** pueden no requerir este flujo.

---

## 7. Gestión de clientes

Módulo **Gestión de clientes** (si está permitido).

- Listado con búsqueda/filtros habituales (nombre, documento, etc., según pantalla).
- **Crear / editar** ficha: datos personales, documento, contacto, redes, emergencia, menor/tutor si aplica.
- Coherencia con validaciones de la API (fechas de expedición, TI solo menor, etc.).
- Posibilidad de abrir **lectura de contrato** firmado cuando exista vínculo (`open_contract_read`), según acciones en tabla.

---

## 8. Gestión contratos (plantillas)

Módulo **Gestión contratos**.

- Lista de **plantillas** por tipo (**tatuaje** / **piercing**).
- Crear o editar contenido **HTML** enriquecido (variables tipo `{{nombres}}`, documento, tutor, etc., según plantilla).
- Marcar plantilla **activa** para uso en firma (advertencias si hay más de una activa por tipo).

---

## 9. Reporte — Finanzas y encuestas

Módulo **Reporte**. Dentro, un selector de **sección**:

### 9.1 Finanzas — citas

- Tabla / métricas sobre citas según **filtros** (nombre, servicio, estado, rango de fechas).
- Exportación típica a **Excel** (según implementación actual).
- Ayuda a conciliar **montos**, abonos y estados operativos.

### 9.2 Encuestas — satisfacción

- **Resumen por pregunta**: estadísticas agregadas según el tipo de cada pregunta (escala 1–5, sí/no, opciones, número, texto).
- Visualizaciones cuando aplica (gráficos tipo torta/barras).

Los datos provienen de las encuestas guardadas al completar el cuestionario en el flujo de firma (y reglas del backend).

---

## 10. Gestión encuesta (administrador de preguntas)

Módulo **Gestión encuesta**.

- CRUD lógico de **preguntas** con:
  - **Tipo** (escala 1–5, sí/no, texto, textarea, numérico, radio, checkbox, select, etc.).
  - **Opciones** (líneas de texto) para tipos que las requieren.
  - **Alcance**: `tattoo`, `piercing` o `both` (qué citas muestran esa pregunta en el cuestionario previo a firmar).
  - **Orden** y estado activo/inactivo.
- Importante para negocio: una pregunta con opciones de **procedimiento** puede enlazarse en backend con **PDF de cuidados/consentimiento** al firmar contrato piercing (tabla `procedure_consent_documents` + webhook `contract_consent_pdf` hacia n8n).

---

## 11. Gestión de usuarios

Visible solo para **administrador** (y sesiones con acceso total si la configuración lo permite).

- Listado de usuarios del panel (activos/inactivos, rol, tienda).
- **Crear usuario**: nombre, usuario, contraseña, tienda, rol.
- **Editar**: mismos datos y estado.
- **Módulos permitidos** (checkboxes): `citas`, `clientes`, `contratos`, `encuestas`, `reporte`. Los **administradores** tienen acceso completo a módulos operativos sin marcar casillas; el resto **debe** tener al menos un módulo para usar el panel operativo.
- Documentación en pantalla (expanders) sobre buenas prácticas de permisos.

---

## 12. Sidebar — herramientas comunes

- **Probar conexión**: `GET` de citas contra la API para validar URL y servidor.
- **Verificar n8n**: comprueba el endpoint de salud/configuración expuesto por la API para integraciones.

---

## 13. Integraciones (referencia para usuario avanzado)

- **n8n**: recibe webhooks según eventos (creación de cita, recibos PDF, contrato firmado, consentimiento PDF por procedimiento, encuestas con baja valoración, etc.). La disponibilidad depende de variables en `.env` del servidor API.

---

## 14. Buenas prácticas

1. Mantén **montos** actualizados antes de pedir **firma de contrato**.
2. Configura **preguntas de encuesta** y **plantillas de contrato** antes de picos de demanda.
3. Para piercing con envío de **PDF de cuidados**, asegura que las **etiquetas de opción** coincidan con los documentos cargados en base de datos y que la encuesta capture el procedimiento correcto.
4. Usa usuarios con **mínimo privilegio**: solo los módulos necesarios por persona.

---

*Documento de referencia del panel operativo (UI Angular + API). Ajustar capturas y procedimientos internos de tu tienda si el despliegue difiere.*

---

## PDF por rol

Para generar manuales en PDF **adaptados por rol** (administrador, vendedor, perforador, tatuador), desde la raíz del repositorio:

```bash
python scripts/build_manual_pdfs_by_role.py
```

Los archivos se escriben en `docs/manual-por-rol/`:

- `manual-panel-administrador.pdf`
- `manual-panel-vendedor.pdf`
- `manual-panel-perforador.pdf`
- `manual-panel-tatuador.pdf`

Opcional: solo algunos roles:

```bash
python scripts/build_manual_pdfs_by_role.py --roles administrador vendedor
```

Requiere **PyMuPDF** (`pymupdf`, ya en `requirements.txt`).
