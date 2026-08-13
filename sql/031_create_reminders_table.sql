-- 031_create_reminders_table.sql
-- Recordatorios de control de cicatrización enviados por WhatsApp.
-- Idempotente: CREATE TABLE IF NOT EXISTS.

USE cherry_tatto;

CREATE TABLE IF NOT EXISTS reminders (
    id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id   BIGINT UNSIGNED NOT NULL COMMENT 'referencia al cliente del servicio',
    customer_name VARCHAR(255)    NOT NULL,
    phone         VARCHAR(20)     NOT NULL COMMENT 'número en formato internacional sin +',
    service_type  ENUM('piercing','tattoo') NOT NULL,
    service_date  DATETIME        NOT NULL COMMENT 'fecha en que se realizó el servicio',
    reminder_date DATE            NOT NULL COMMENT 'fecha programada para enviar el recordatorio',
    status        ENUM('pending','sent') NOT NULL DEFAULT 'pending',
    sent_at       TIMESTAMP       NULL DEFAULT NULL COMMENT 'fecha real de envío',
    created_at    TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_reminders_status_date (status, reminder_date),
    INDEX idx_reminders_customer    (customer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;