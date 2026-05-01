-- Tipos de plantilla: tattoo | piercing; una activa por tipo.
-- Conviven versiones por (contract_kind, name, version).
--
-- Idempotente: puede volver a ejecutarse si un paso falló antes.
-- El índice único antiguo puede llamarse distinto o ya no existir.

SET NAMES utf8mb4;

SET @db := DATABASE();

-- 1) Columna contract_kind
SET @col_exists := (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = @db
    AND TABLE_NAME = 'contract_templates'
    AND COLUMN_NAME = 'contract_kind'
);
SET @sql := IF(
  @col_exists = 0,
  'ALTER TABLE contract_templates ADD COLUMN contract_kind VARCHAR(20) NOT NULL DEFAULT ''tattoo'' COMMENT ''tattoo | piercing'' AFTER name',
  'SELECT ''010: contract_kind ya existe'' AS migracion_010_msg'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 2) Quitar UNIQUE antiguo solo sobre (name, version) — nombre libre en el esquema
SET @old_idx := (
  SELECT s.INDEX_NAME
  FROM INFORMATION_SCHEMA.STATISTICS s
  WHERE s.TABLE_SCHEMA = @db
    AND s.TABLE_NAME = 'contract_templates'
    AND s.INDEX_NAME != 'PRIMARY'
  GROUP BY s.INDEX_NAME
  HAVING MAX(s.NON_UNIQUE) = 0
    AND GROUP_CONCAT(s.COLUMN_NAME ORDER BY s.SEQ_IN_INDEX SEPARATOR ',') = 'name,version'
  LIMIT 1
);
SET @sql := IF(
  @old_idx IS NOT NULL,
  CONCAT('ALTER TABLE contract_templates DROP INDEX `', @old_idx, '`'),
  'SELECT ''010: no hay UNIQUE antiguo (name,version); omitido'' AS migracion_010_msg'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 3) Nuevo UNIQUE (contract_kind, name, version)
SET @new_exists := (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = @db
    AND TABLE_NAME = 'contract_templates'
    AND INDEX_NAME = 'uk_tpl_kind_name_version'
);
SET @sql := IF(
  @new_exists = 0,
  'ALTER TABLE contract_templates ADD UNIQUE KEY uk_tpl_kind_name_version (contract_kind, name, version)',
  'SELECT ''010: uk_tpl_kind_name_version ya existe'' AS migracion_010_msg'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
