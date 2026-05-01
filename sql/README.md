# SQL migrations - cherry_tatto

Esta carpeta contiene scripts SQL para crear la estructura base y aplicar cambios incrementales.

## Orden recomendado (entorno nuevo)

1. `000_initial_schema_cherry_tatto.sql`
2. `002_customer_document_issue_date.sql`
3. `003_contract_signature_assets.sql`
4. `004_appointment_status_workflow.sql`
5. `005_appointment_financial_fields.sql`
6. `006_appointment_payments_traceability.sql`
7. `007_relax_minor_guardian_check.sql` (solo si existe el CHECK `chk_customers_minor_guardian`; ver nota en el script)
8. `008_customer_social_media_varchar50.sql` (si aplica a tu entorno)
9. `009_drop_customers_secondary_email.sql` (si aplica)
10. `010_contract_templates_contract_kind.sql` (plantillas por tipo tattoo/piercing; idempotente)
11. `011_survey_questions_and_answers.sql` (preguntas configurables y respuestas por encuesta; incluye `ALTER` en `surveys.id` para evitar error 3780 de FK en MySQL 8 si el tipo de `id` no era `BIGINT UNSIGNED`)
12. `012_survey_question_formats_options_number.sql` (solo si ya ejecutaste un `011` antiguo: añade `options_json`, `answer_number` y amplía tipos: radio, checkbox, select, textarea, texto corto, numérico)
13. `013_survey_questions_contract_kind.sql` (columna **tatuaje / piercing** por pregunta; el cuestionario de firma filtra según el tipo de cita)
14. `014_survey_questions_scope_both.sql` (solo si aplicaste un `013` anterior sin `both`: permite ámbito **tatuaje y piercing**)

> Nota: `001_customers_and_appointments_fk.sql` queda como referencia histórica porque la estructura base ya está consolidada en `000_initial_schema_cherry_tatto.sql`.

## Orden recomendado (entorno existente)

Si tu base ya existe y solo quieres actualizar:

1. `002_customer_document_issue_date.sql`
2. `003_contract_signature_assets.sql`
3. `004_appointment_status_workflow.sql`
4. `005_appointment_financial_fields.sql`
5. `006_appointment_payments_traceability.sql`
6. `007_relax_minor_guardian_check.sql` (opcional, según el script)
7. `008_customer_social_media_varchar50.sql`
8. `009_drop_customers_secondary_email.sql`
9. `010_contract_templates_contract_kind.sql`
10. `011_survey_questions_and_answers.sql`
11. `012_survey_question_formats_options_number.sql` (omitir si tu `011` ya incluye columnas y CHECK ampliados)
12. `013_survey_questions_contract_kind.sql`
13. `014_survey_questions_scope_both.sql` (omitir si tu `013` o `recreate_survey_tables` ya incluye `both` en el CHECK)

## Recuperación rápida

Si borraste las tablas de encuesta y necesitas volver a crear **`surveys`**, **`survey_questions`** y **`survey_answers`** (sin datos), ejecuta:

- `recreate_survey_tables.sql`

Haz backup antes; el script hace `DROP` de esas tres tablas y las crea de nuevo. Incluye **quitar y recrear** las FK de `contracts` y `appointment_payments` hacia `appointments`, y alinear `appointment_id` / `id` a **BIGINT UNSIGNED**, para evitar el error **3780** cuando la base tenía tipos mezclados.

## Rollback de datos (no estructura)

Para vaciar toda la data del esquema `cherry_tatto` sin borrar tablas:

- Ejecuta `000_rollback_purge_data_cherry_tatto.sql`

Este script:
- desactiva temporalmente `FOREIGN_KEY_CHECKS`,
- hace `TRUNCATE` de tablas de negocio,
- y restaura `FOREIGN_KEY_CHECKS`.

## Recomendaciones

- Para cargar **30 citas de prueba** con contrato firmado, encuesta respondida y respuestas variadas (métricas del reporte **Encuestas**), ejecuta desde la raíz del repo: `python scripts/seed_demo_surveys.py` (opciones `--count` y `--clean` en la cabecera del script).
- Ejecuta scripts en una sesión con permisos de `ALTER`, `CREATE`, `INDEX`, `REFERENCES` y `TRUNCATE`.
- Haz backup antes de correr scripts en producción.
- Si usas MySQL Workbench con `safe updates`, los scripts `004` y `005` ya contemplan compatibilidad.
