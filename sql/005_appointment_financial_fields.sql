-- Campos financieros para control de cita.
-- Idempotente: columnas condicionales; los UPDATE son seguros al repetir.

SET @has_total := (
    SELECT COUNT(*)
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'appointments'
      AND column_name = 'total_amount'
);
SET @ddl_total := IF(
    @has_total = 0,
    "ALTER TABLE appointments ADD COLUMN total_amount DECIMAL(12,2) NOT NULL DEFAULT 0.00 AFTER deposit",
    "SELECT 1"
);
PREPARE stmt_total FROM @ddl_total;
EXECUTE stmt_total;
DEALLOCATE PREPARE stmt_total;

SET @has_pending := (
    SELECT COUNT(*)
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'appointments'
      AND column_name = 'pending_balance'
);
SET @ddl_pending := IF(
    @has_pending = 0,
    "ALTER TABLE appointments ADD COLUMN pending_balance DECIMAL(12,2) NOT NULL DEFAULT 0.00 AFTER total_amount",
    "SELECT 1"
);
PREPARE stmt_pending FROM @ddl_pending;
EXECUTE stmt_pending;
DEALLOCATE PREPARE stmt_pending;

SET @has_credit := (
    SELECT COUNT(*)
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'appointments'
      AND column_name = 'customer_credit'
);
SET @ddl_credit := IF(
    @has_credit = 0,
    "ALTER TABLE appointments ADD COLUMN customer_credit DECIMAL(12,2) NOT NULL DEFAULT 0.00 AFTER pending_balance",
    "SELECT 1"
);
PREPARE stmt_credit FROM @ddl_credit;
EXECUTE stmt_credit;
DEALLOCATE PREPARE stmt_credit;

-- Normaliza datos actuales:
-- Si no hay total registrado, usar el abonado como base.
SET @prev_safe_updates := @@SQL_SAFE_UPDATES;
SET SQL_SAFE_UPDATES = 0;

UPDATE appointments
SET total_amount = COALESCE(total_amount, 0.00)
WHERE total_amount IS NULL;

UPDATE appointments
SET pending_balance = GREATEST(COALESCE(total_amount, 0.00) - COALESCE(deposit, 0.00), 0.00);

SET SQL_SAFE_UPDATES = @prev_safe_updates;
