-- Profesional asignado a la cita (tatuador o perforador, tabla panel_users).
-- Requiere haber aplicado 015_panel_users.sql. La disponibilidad por hora es por profesional.

USE cherry_tatto;

ALTER TABLE appointments
    ADD COLUMN assigned_panel_user_id BIGINT UNSIGNED NULL
        COMMENT 'Tatuador o perforador segun tipo de servicio'
        AFTER customer_id;

CREATE INDEX idx_appointments_assigned_panel_user ON appointments (assigned_panel_user_id);

ALTER TABLE appointments
    ADD CONSTRAINT fk_appointments_assigned_panel_user
        FOREIGN KEY (assigned_panel_user_id) REFERENCES panel_users (id)
        ON DELETE SET NULL ON UPDATE CASCADE;
