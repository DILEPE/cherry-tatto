-- Trazabilidad de abonos por cita.
-- Ejecutar una vez en bases existentes.
-- Usa el mismo tipo de appointments.id para evitar incompatibilidades de FK.

SET @appt_id_type := (
    SELECT COLUMN_TYPE
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'appointments'
      AND column_name = 'id'
    LIMIT 1
);

SET @ddl_create_payments := CONCAT(
    'CREATE TABLE IF NOT EXISTS appointment_payments (',
    'id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,',
    'appointment_id ', IFNULL(@appt_id_type, 'BIGINT UNSIGNED'), ' NOT NULL,',
    'amount DECIMAL(12,2) NOT NULL,',
    'note VARCHAR(300) NULL,',
    'created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,',
    'PRIMARY KEY (id),',
    'INDEX idx_appointment_payments_appointment_id (appointment_id),',
    'CONSTRAINT fk_appointment_payments_appointment ',
    'FOREIGN KEY (appointment_id) REFERENCES appointments (id) ',
    'ON DELETE CASCADE ON UPDATE CASCADE',
    ') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'
);

PREPARE stmt_create_payments FROM @ddl_create_payments;
EXECUTE stmt_create_payments;
DEALLOCATE PREPARE stmt_create_payments;

-- Backfill inicial: convierte abonos existentes en historial.
INSERT INTO appointment_payments (appointment_id, amount, note)
SELECT a.id, a.deposit, 'Abono inicial migrado'
FROM appointments a
LEFT JOIN appointment_payments p ON p.appointment_id = a.id
WHERE COALESCE(a.deposit, 0) > 0
  AND p.id IS NULL;
