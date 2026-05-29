-- Fecha efectiva opcional por abono (además de created_at).

SELECT COUNT(*) INTO @missing_paid_on
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'appointment_payments'
  AND COLUMN_NAME = 'paid_on'
LIMIT 1;

SET @sql_paid_on := IF(
    IFNULL(@missing_paid_on, 0) >= 1,
    'SELECT 1 AS skip_appointment_payments_paid_on',
    'ALTER TABLE appointment_payments ADD COLUMN paid_on DATE NULL COMMENT ''Fecha en que el cliente abona'' AFTER note'
);
PREPARE stmt_paid_on FROM @sql_paid_on;
EXECUTE stmt_paid_on;
DEALLOCATE PREPARE stmt_paid_on;
