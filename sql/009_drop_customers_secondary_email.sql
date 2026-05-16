-- Elimina el correo secundario del cliente (ya no se usa en API ni formularios).
-- Idempotente: solo DROP COLUMN si secondary_email existe.

USE cherry_tatto;

SET @db := DATABASE();

SET @has_secondary_email := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @db
      AND TABLE_NAME = 'customers'
      AND COLUMN_NAME = 'secondary_email'
);

SET @sql_drop_secondary_email := IF(
    @has_secondary_email > 0,
    'ALTER TABLE customers DROP COLUMN secondary_email',
    'SELECT 1 AS skip_drop_secondary_email'
);

PREPARE _stmt_drop_secondary_email FROM @sql_drop_secondary_email;
EXECUTE _stmt_drop_secondary_email;
DEALLOCATE PREPARE _stmt_drop_secondary_email;
