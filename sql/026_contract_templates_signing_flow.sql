-- Flujo de firma por plantilla: phased (3 pasos) | single (una pantalla).
-- Idempotente.
-- En MySQL Workbench: ejecutar con la BD seleccionada o dejar el USE de abajo.

USE cherry_tatto;

SET @db := DATABASE();

SET @has_col := (
  SELECT COUNT(*)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @db
    AND TABLE_NAME = 'contract_templates'
    AND COLUMN_NAME = 'signing_flow'
);

SET @sql_add_col := IF(
  @has_col = 0,
  "ALTER TABLE contract_templates
     ADD COLUMN signing_flow VARCHAR(16) NOT NULL DEFAULT 'phased'
     COMMENT 'phased = 3 etapas; single = datos + encuesta + firma en una pantalla'
     AFTER is_active",
  "SELECT '026: signing_flow ya existe' AS migracion_026_msg"
);
PREPARE _stmt FROM @sql_add_col;
EXECUTE _stmt;
DEALLOCATE PREPARE _stmt;

SET @has_chk := (
  SELECT COUNT(*)
  FROM information_schema.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = @db
    AND TABLE_NAME = 'contract_templates'
    AND CONSTRAINT_NAME = 'chk_contract_templates_signing_flow'
);

SET @sql_chk := IF(
  @has_chk = 0,
  "ALTER TABLE contract_templates
     ADD CONSTRAINT chk_contract_templates_signing_flow
     CHECK (signing_flow IN ('phased', 'single'))",
  "SELECT '026: chk signing_flow ya existe' AS migracion_026_msg"
);
PREPARE _stmt2 FROM @sql_chk;
EXECUTE _stmt2;
DEALLOCATE PREPARE _stmt2;
