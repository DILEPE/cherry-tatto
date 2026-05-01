-- Estandariza estados de citas para flujo operativo.
-- Ejecutar una vez en bases existentes.

SET @has_status := (
    SELECT COUNT(*)
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'appointments'
      AND column_name = 'status'
);
SET @ddl := IF(
    @has_status = 0,
    "ALTER TABLE appointments ADD COLUMN status VARCHAR(30) NOT NULL DEFAULT 'Agendada' AFTER deposit",
    "SELECT 1"
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- Asegura compatibilidad de valores de estado (evita truncamiento si antes era ENUM).
ALTER TABLE appointments
    MODIFY COLUMN status VARCHAR(30) NOT NULL DEFAULT 'Agendada';

-- Normaliza estados históricos.
SET @prev_safe_updates := @@SQL_SAFE_UPDATES;
SET SQL_SAFE_UPDATES = 0;

UPDATE appointments
SET status = 'Finalizada'
WHERE id IN (
    SELECT x.id
    FROM (
        SELECT id
        FROM appointments
        WHERE status IN ('Completado', 'Completed')
    ) AS x
);

UPDATE appointments
SET status = 'Agendada'
WHERE id IN (
    SELECT x.id
    FROM (
        SELECT id
        FROM appointments
        WHERE status IS NULL OR TRIM(status) = ''
    ) AS x
);

SET SQL_SAFE_UPDATES = @prev_safe_updates;
