# SQL migrations - cherry_tatto

Esta carpeta contiene scripts SQL para crear la estructura base y aplicar cambios incrementales.

## Orden recomendado (entorno nuevo)

1. `000_initial_schema_cherry_tatto.sql`
2. `002_customer_document_issue_date.sql`
3. `003_contract_signature_assets.sql`
4. `004_appointment_status_workflow.sql`
5. `005_appointment_financial_fields.sql`
6. `006_appointment_payments_traceability.sql`

> Nota: `001_customers_and_appointments_fk.sql` queda como referencia histórica porque la estructura base ya está consolidada en `000_initial_schema_cherry_tatto.sql`.

## Orden recomendado (entorno existente)

Si tu base ya existe y solo quieres actualizar:

1. `002_customer_document_issue_date.sql`
2. `003_contract_signature_assets.sql`
3. `004_appointment_status_workflow.sql`
4. `005_appointment_financial_fields.sql`
5. `006_appointment_payments_traceability.sql`

## Rollback de datos (no estructura)

Para vaciar toda la data del esquema `cherry_tatto` sin borrar tablas:

- Ejecuta `000_rollback_purge_data_cherry_tatto.sql`

Este script:
- desactiva temporalmente `FOREIGN_KEY_CHECKS`,
- hace `TRUNCATE` de tablas de negocio,
- y restaura `FOREIGN_KEY_CHECKS`.

## Recomendaciones

- Ejecuta scripts en una sesión con permisos de `ALTER`, `CREATE`, `INDEX`, `REFERENCES` y `TRUNCATE`.
- Haz backup antes de correr scripts en producción.
- Si usas MySQL Workbench con `safe updates`, los scripts `004` y `005` ya contemplan compatibilidad.
