-- 034_appointment_signing_ot.sql
-- Código OTP numérico de 6 dígitos para que el cliente firme contrato/encuesta.
-- Idempotente: CREATE TABLE IF NOT EXISTS.

USE cherry_tatto;

CREATE TABLE IF NOT EXISTS appointment_signing_ot (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    appointment_id  BIGINT UNSIGNED NOT NULL,
    customer_id     BIGINT UNSIGNED NOT NULL,
    code            CHAR(6)         NOT NULL COMMENT 'código numérico de 6 dígitos',
    created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    consumed_at     TIMESTAMP       NULL DEFAULT NULL COMMENT 'cuando el cliente firmó el contrato',
    revoked_at      TIMESTAMP       NULL DEFAULT NULL COMMENT 'reemplazado por un código nuevo',
    PRIMARY KEY (id),
    UNIQUE KEY uq_appointment_signing_ot_code (code),
    INDEX idx_signing_ot_appointment (appointment_id),
    INDEX idx_signing_ot_active (appointment_id, consumed_at, revoked_at),
    CONSTRAINT fk_signing_ot_appointment
        FOREIGN KEY (appointment_id) REFERENCES appointments (id),
    CONSTRAINT fk_signing_ot_customer
        FOREIGN KEY (customer_id) REFERENCES customers (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
