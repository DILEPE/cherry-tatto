# Scripts de refactor del tab Citas (`citas_tab.py`)

Utilidades **puntuales** usadas al extraer el monolito `streamlit_app/citas_tab.py` hacia la arquitectura modular descrita en [`.cursor/rules/streamlit-tab-architecture.mdc`](../.cursor/rules/streamlit-tab-architecture.mdc).

No forman parte del arranque diario del proyecto. Sirven para **regenerar** o **podar** código si vuelves a mover bloques grandes desde `citas_tab.py` (por ejemplo, antes de abrir un PR de refactor).

## Cuándo usarlos

| Situación | Acción |
|-----------|--------|
| Edición normal de la app | Edita los módulos finales (`citas_agendar_*`, `citas_detail_dialogs`, etc.) a mano. **No** ejecutes estos scripts. |
| Nuevo bloque copiado temporalmente a `citas_tab.py` | Ajusta rangos de línea en el script correspondiente, ejecuta, revisa `git diff` y `py_compile`. |
| Regenerar un módulo desde el tab (histórico) | Solo si el tab sigue conteniendo el código fuente en los rangos documentados abajo. |

**Siempre** revisa el diff y ejecuta:

```powershell
python -m py_compile streamlit_app/citas_tab.py streamlit_app/citas_agendar_dialog.py streamlit_app/citas_detail_dialogs.py streamlit_app/reporte_finanzas_citas.py
```

## Orden recomendado (refactor por fases)

Los scripts de esta carpeta asumen que **ya** existen CSS, componentes y calendario (PR previo). Para el diálogo de foco del calendario existe otro generador:

1. [`gen_calendar_focus_dialogs.py`](gen_calendar_focus_dialogs.py) — genera `components/calendar_focus_dialogs.py` anclando a símbolos en `citas_tab.py` (actualizar anclas si el tab cambió).

2. [`_extract_modules.py`](_extract_modules.py) — escribe de una vez:
   - `citas_row_policy.py`
   - `citas_detail_dialogs.py` (rangos fijos en `citas_tab.py`)
   - `survey_question_stats_report.py`
   - `reporte_finanzas_citas.py` (requiere revisión manual de firma de `render_reporte_financiero_citas_body`)

3. [`_build_citas_extractions.py`](_build_citas_extractions.py) — monta un borrador de `citas_agendar_dialog.py` concatenando trozos del tab (rangos 1-based en el script).

4. [`prune_citas_tab_ranges.py`](prune_citas_tab_ranges.py) — **elimina** del tab los bloques ya movidos. **Actualiza `RANGES_DESC`** antes de ejecutar; los números de línea del tab cambian tras cada poda.

5. Ajuste manual: modularizar agendar en `citas_agendar_state`, `citas_agendar_sections`, `citas_agendar_submit`, etc. (estado actual del repo).

[`split_citas_tab_phase2.py`](split_citas_tab_phase2.py) es un **borrador alternativo** de la fase 2; termina en `SystemExit(1)` y no debe ejecutarse en CI. Conservado como referencia de rangos y reemplazos.

## Detalle por script

### `_extract_modules.py`

```powershell
python scripts/_extract_modules.py
```

- **Entrada:** `streamlit_app/citas_tab.py` con el código aún en los rangos codificados en el script.
- **Salida:** sobrescribe `citas_row_policy.py`, `citas_detail_dialogs.py`, `survey_question_stats_report.py`, `reporte_finanzas_citas.py`.
- **Nota:** imprime aviso de revisar la firma del reporte financiero (`client_history_key`, `render_row_actions`).

### `_build_citas_extractions.py`

```powershell
python scripts/_build_citas_extractions.py
```

- **Entrada:** rangos en `citas_tab.py`: 98–182, 783–855, 858–1323 (líneas 1-based, inclusivas).
- **Salida:** sobrescribe `citas_agendar_dialog.py` (monolito; el repo actual lo partió además en `citas_agendar_*`).
- Renombra prefijos `_` → API pública y sustituye imports (`format_http_error_detail`, etc.).

### `prune_citas_tab_ranges.py`

```powershell
python scripts/prune_citas_tab_ranges.py
```

- **Efecto:** borra líneas del tab según `RANGES_DESC` (orden descendente por inicio).
- **Rangos usados en el refactor del PR #69** (ya aplicados; no re-ejecutar sin restaurar el tab):

  | Inicio | Fin | Contenido movido (aprox.) |
  |--------|-----|---------------------------|
  | 98 | 182 | helpers booking / cliente |
  | 372 | 442 | helpers detalle / work kind |
  | 510 | 516 | fragmentos huérfanos |
  | 541 | 591 | reprogram policy duplicada |
  | 659 | 669 | … |
  | 686 | 713 | … |
  | 770 | 781 | … |
  | 783 | 854 | estado formulario agendar |
  | 859 | 1324 | diálogo agendar |
  | 1523 | 1971 | diálogos detalle |
  | 2003 | 2362 | reporte + encuestas |

Tras cada ejecución, **recalcula** los rangos restantes o el siguiente script fallará.

### `split_citas_tab_phase2.py`

- Variante experimental; **aborta** a propósito (`raise SystemExit(1)`).
- Útil solo para leer cómo se intentó extraer reporte/detalle; no usar en flujo automatizado.

### `gen_calendar_focus_dialogs.py` (relacionado)

```powershell
python scripts/gen_calendar_focus_dialogs.py
```

- Regenera `streamlit_app/components/calendar_focus_dialogs.py`.
- Anclas actuales: `def _render_calendar_focus_appointment_body`, `@st.dialog("Citas del día"`, `def _get_appointment_payments_cached`.
- Si el tab ya no tiene esos símbolos, actualiza el script antes de ejecutar.

## Módulos destino (referencia)

| Módulo | Responsabilidad |
|--------|-----------------|
| `citas_agendar_dialog.py` | `@st.dialog` + orquestación |
| `citas_agendar_state.py` | `ap_*`, init/reset, cola de éxito |
| `citas_agendar_sections.py` | `render_agendar_booking_form_body` y bloques |
| `citas_agendar_submit.py` | POST crear cita, pie Crear/Cancelar |
| `citas_agendar_helpers.py` / `citas_agendar_pure.py` / `citas_agendar_customer.py` | helpers puros y cliente |
| `citas_detail_dialogs.py` | reprogramar, montos, anular, recibos |
| `reporte_finanzas_citas.py` | cuerpo finanzas del Reporte |
| `survey_question_stats_report.py` | encuestas del Reporte |
| `citas_booking_meta.py`, `citas_schedule_queries.py`, `citas_panel_staff.py`, `citas_row_policy.py` | meta agenda / ocupación / staff / políticas |

## Historial

Introducidos en el refactor **Streamlit Citas: arquitectura modular** (rama `feature/streamlit-tab-arquitectura-css-componentes`, PR hacia `develop`).
