-- Profesional asignado a la cita (tatuador o perforador, tabla panel_users).
-- Requiere haber aplicado 015_panel_users.sql.
-- Idempotente.

USE cherry_tatto;

SET @db := DATABASE();

SET @has_col := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @db
      AND TABLE_NAME = 'appointments'
      AND COLUMN_NAME = 'assigned_panel_user_id'
);

SET @sql := IF(
    @has_col = 0,
    'ALTER TABLE appointments ADD COLUMN assigned_panel_user_id BIGINT UNSIGNED NULL COMMENT ''Tatuador o perforador segun tipo de servicio'' AFTER customer_id',
    'SELECT 1 AS skip_assigned_panel_user_id'
);
PREPARE _s FROM @sql;
EXECUTE _s;
DEALLOCATE PREPARE _s;

SET @has_idx := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = @db
      AND TABLE_NAME = 'appointments'
      AND INDEX_NAME = 'idx_appointments_assigned_panel_user'
);

SET @sql := IF(
    @has_idx = 0,
    'CREATE INDEX idx_appointments_assigned_panel_user ON appointments (assigned_panel_user_id)',
    'SELECT 1 AS skip_idx_appointments_assigned_panel_user'
);
PREPARE _s FROM @sql;
EXECUTE _s;
DEALLOCATE PREPARE _s;

SET @has_fk := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = @db
      AND TABLE_NAME = 'appointments'
      AND CONSTRAINT_NAME = 'fk_appointments_assigned_panel_user'
      AND CONSTRAINT_TYPE = 'FOREIGN KEY'
);

SET @sql := IF(
    @has_fk = 0,
    'ALTER TABLE appointments ADD CONSTRAINT fk_appointments_assigned_panel_user FOREIGN KEY (assigned_panel_user_id) REFERENCES panel_users (id) ON DELETE SET NULL ON UPDATE CASCADE',
    'SELECT 1 AS skip_fk_appointments_assigned_panel_user'
);
PREPARE _s FROM @sql;
EXECUTE _s;
DEALLOCATE PREPARE _s;
