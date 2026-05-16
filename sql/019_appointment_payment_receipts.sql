-- Recibos de pago en PDF por cita (vinculados opcionalmente a fila de appointment_payments).
-- Ejecutar tras 006_appointment_payments_traceability.sql (tabla appointment_payments).

CREATE TABLE IF NOT EXISTS appointment_payment_receipts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    appointment_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NULL,
    appointment_payment_id BIGINT UNSIGNED NULL,
    kind VARCHAR(24) NOT NULL COMMENT 'inicial | abono',
    amount DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    total_amount_snapshot DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    deposit_after DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    pending_after DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    note VARCHAR(500) NULL,
    file_name VARCHAR(255) NOT NULL,
    pdf MEDIUMBLOB NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_apr_appointment (appointment_id),
    INDEX idx_apr_payment (appointment_payment_id),
    CONSTRAINT fk_apr_appointment
        FOREIGN KEY (appointment_id) REFERENCES appointments (id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_apr_customer
        FOREIGN KEY (customer_id) REFERENCES customers (id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
