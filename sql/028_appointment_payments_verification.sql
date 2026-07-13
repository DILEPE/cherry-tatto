-- Verificación de abonos por administrador (antes de firmar contrato).
-- Idempotente.

USE cherry_tatto;

SET @db := DATABASE();

SET @has_is_verified := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @db
      AND TABLE_NAME = 'appointment_payments'
      AND COLUMN_NAME = 'is_verified'
);

SET @sql_is_verified := IF(
    @has_is_verified > 0,
    'SELECT 1 AS skip_is_verified',
    'ALTER TABLE appointment_payments ADD COLUMN is_verified TINYINT(1) NOT NULL DEFAULT 0 AFTER paid_on'
);
PREPARE _stmt_is_verified FROM @sql_is_verified;
EXECUTE _stmt_is_verified;
DEALLOCATE PREPARE _stmt_is_verified;

SET @has_verified_at := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @db
      AND TABLE_NAME = 'appointment_payments'
      AND COLUMN_NAME = 'verified_at'
);

SET @sql_verified_at := IF(
    @has_verified_at > 0,
    'SELECT 1 AS skip_verified_at',
    'ALTER TABLE appointment_payments ADD COLUMN verified_at DATETIME NULL DEFAULT NULL AFTER is_verified'
);
PREPARE _stmt_verified_at FROM @sql_verified_at;
EXECUTE _stmt_verified_at;
DEALLOCATE PREPARE _stmt_verified_at;

SET @has_verified_by := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @db
      AND TABLE_NAME = 'appointment_payments'
      AND COLUMN_NAME = 'verified_by'
);

SET @sql_verified_by := IF(
    @has_verified_by > 0,
    'SELECT 1 AS skip_verified_by',
    'ALTER TABLE appointment_payments ADD COLUMN verified_by BIGINT UNSIGNED NULL DEFAULT NULL AFTER verified_at'
);
PREPARE _stmt_verified_by FROM @sql_verified_by;
EXECUTE _stmt_verified_by;
DEALLOCATE PREPARE _stmt_verified_by;

-- Abonos ya existentes: marcar verificados para no bloquear citas pagadas previas.
-- Incluye `id` en el WHERE para cumplir safe update mode (MySQL Workbench error 1175).
UPDATE appointment_payments
SET is_verified = 1,
    verified_at = COALESCE(verified_at, created_at)
WHERE id > 0
  AND is_verified = 0;
