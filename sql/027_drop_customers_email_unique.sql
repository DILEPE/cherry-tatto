-- Permite reutilizar el mismo correo en varios clientes (p. ej. al agendar).
-- Idempotente: solo DROP INDEX si uk_customers_email existe.

USE cherry_tatto;

SET @db := DATABASE();

SET @has_uk_email := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = @db
      AND TABLE_NAME = 'customers'
      AND INDEX_NAME = 'uk_customers_email'
);

SET @sql_drop_uk_email := IF(
    @has_uk_email > 0,
    'ALTER TABLE customers DROP INDEX uk_customers_email',
    'SELECT 1 AS skip_drop_uk_customers_email'
);

PREPARE _stmt_drop_uk_email FROM @sql_drop_uk_email;
EXECUTE _stmt_drop_uk_email;
DEALLOCATE PREPARE _stmt_drop_uk_email;
