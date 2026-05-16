-- Permitir insertar menores sin tutor completo (completar después del agendamiento o en administración).
-- Idempotente: solo hace DROP CHECK si existe chk_customers_minor_guardian.

USE cherry_tatto;

SET @db := DATABASE();

SET @has_chk_minor := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = @db
      AND TABLE_NAME = 'customers'
      AND CONSTRAINT_NAME = 'chk_customers_minor_guardian'
      AND CONSTRAINT_TYPE = 'CHECK'
);

SET @sql_drop_chk_minor := IF(
    @has_chk_minor > 0,
    'ALTER TABLE customers DROP CHECK chk_customers_minor_guardian',
    'SELECT 1 AS skip_drop_chk_customers_minor_guardian'
);

PREPARE _stmt_drop_chk_minor FROM @sql_drop_chk_minor;
EXECUTE _stmt_drop_chk_minor;
DEALLOCATE PREPARE _stmt_drop_chk_minor;
