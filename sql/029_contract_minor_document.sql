-- Fotos del documento de identidad del menor en contratos firmados.
-- Idempotente: cada columna solo se añade si falta.
-- En MySQL Workbench: ejecuta con la base seleccionada, o deja USE cherry_tatto;

USE cherry_tatto;

SET @db := DATABASE();

-- minor_document_front
SET @c := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'contracts' AND COLUMN_NAME = 'minor_document_front'
);
SET @sql := IF(
    @c = 0,
    'ALTER TABLE contracts ADD COLUMN minor_document_front LONGTEXT NULL AFTER tutor_document_back',
    'SELECT 1 AS skip_minor_document_front'
);
PREPARE _s FROM @sql;
EXECUTE _s;
DEALLOCATE PREPARE _s;

-- minor_document_back
SET @c := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'contracts' AND COLUMN_NAME = 'minor_document_back'
);
SET @sql := IF(
    @c = 0,
    'ALTER TABLE contracts ADD COLUMN minor_document_back LONGTEXT NULL AFTER minor_document_front',
    'SELECT 1 AS skip_minor_document_back'
);
PREPARE _s FROM @sql;
EXECUTE _s;
DEALLOCATE PREPARE _s;
