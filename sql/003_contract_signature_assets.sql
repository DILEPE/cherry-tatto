-- Campos adicionales para firma de contrato digital con evidencia de tutor.
-- Idempotente: cada columna solo se añade si falta.

SET @db := DATABASE();

-- artist_signature
SET @c := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'contracts' AND COLUMN_NAME = 'artist_signature'
);
SET @sql := IF(
    @c = 0,
    'ALTER TABLE contracts ADD COLUMN artist_signature LONGTEXT NULL AFTER tutor_signature',
    'SELECT 1 AS skip_artist_signature'
);
PREPARE _s FROM @sql;
EXECUTE _s;
DEALLOCATE PREPARE _s;

-- tutor_document_front
SET @c := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'contracts' AND COLUMN_NAME = 'tutor_document_front'
);
SET @sql := IF(
    @c = 0,
    'ALTER TABLE contracts ADD COLUMN tutor_document_front LONGTEXT NULL AFTER artist_signature',
    'SELECT 1 AS skip_tutor_document_front'
);
PREPARE _s FROM @sql;
EXECUTE _s;
DEALLOCATE PREPARE _s;

-- tutor_document_back
SET @c := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'contracts' AND COLUMN_NAME = 'tutor_document_back'
);
SET @sql := IF(
    @c = 0,
    'ALTER TABLE contracts ADD COLUMN tutor_document_back LONGTEXT NULL AFTER tutor_document_front',
    'SELECT 1 AS skip_tutor_document_back'
);
PREPARE _s FROM @sql;
EXECUTE _s;
DEALLOCATE PREPARE _s;

-- contract_text
SET @c := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'contracts' AND COLUMN_NAME = 'contract_text'
);
SET @sql := IF(
    @c = 0,
    'ALTER TABLE contracts ADD COLUMN contract_text LONGTEXT NULL AFTER tutor_document_back',
    'SELECT 1 AS skip_contract_text'
);
PREPARE _s FROM @sql;
EXECUTE _s;
DEALLOCATE PREPARE _s;
