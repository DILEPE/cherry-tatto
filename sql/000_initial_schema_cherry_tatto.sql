-- Migración 000: estructura base inicial para cherry_tatto
-- Nota: esta base NO incluye columnas agregadas en migraciones incrementales posteriores.

CREATE DATABASE IF NOT EXISTS cherry_tatto
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE cherry_tatto;

-- =========================
-- Tabla: customers
-- =========================
CREATE TABLE IF NOT EXISTS customers (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    birth_date DATE NOT NULL,
    document_type ENUM('CC', 'TI', 'CE', 'PAS') NOT NULL,
    document_number VARCHAR(32) NOT NULL,
    email VARCHAR(255) NOT NULL,
    phone_number VARCHAR(32) NOT NULL,
    address VARCHAR(500) NULL,
    nationality VARCHAR(100) NULL,
    profession VARCHAR(150) NULL,
    secondary_email VARCHAR(255) NULL,
    social_media JSON NULL,
    emergency_contact_name VARCHAR(150) NULL,
    emergency_contact_phone VARCHAR(32) NULL,
    is_minor BOOLEAN NOT NULL DEFAULT FALSE,
    guardian_name VARCHAR(200) NULL,
    guardian_document_type ENUM('CC', 'TI', 'CE', 'PAS') NULL,
    guardian_document_number VARCHAR(32) NULL,
    guardian_document_issue_date DATE NULL,
    deleted_at TIMESTAMP NULL DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_customers_document_number (document_number),
    UNIQUE KEY uk_customers_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_customers_name ON customers (last_name, first_name);
CREATE INDEX idx_customers_deleted ON customers (deleted_at);

-- =========================
-- Tabla: appointments
-- =========================
CREATE TABLE IF NOT EXISTS appointments (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NULL,
    customer_name VARCHAR(200) NOT NULL,
    phone VARCHAR(40) NOT NULL,
    service_type VARCHAR(120) NOT NULL,
    detail TEXT NULL,
    appointment_date DATE NOT NULL,
    deposit DECIMAL(12,2) NOT NULL DEFAULT 0.00,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_appointments_customer_id (customer_id),
    CONSTRAINT fk_appointments_customer
        FOREIGN KEY (customer_id) REFERENCES customers (id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================
-- Tabla: contract_templates
-- =========================
CREATE TABLE IF NOT EXISTS contract_templates (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    name VARCHAR(200) NOT NULL,
    version VARCHAR(50) NOT NULL,
    content LONGTEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_contract_templates_name_version (name, version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================
-- Tabla: contracts
-- =========================
CREATE TABLE IF NOT EXISTS contracts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    appointment_id BIGINT UNSIGNED NOT NULL,
    template_id BIGINT UNSIGNED NULL,
    is_minor BOOLEAN NOT NULL DEFAULT FALSE,
    health_data JSON NULL,
    client_signature LONGTEXT NULL,
    tutor_signature LONGTEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_contracts_appointment_id (appointment_id),
    INDEX idx_contracts_template_id (template_id),
    CONSTRAINT fk_contracts_appointment
        FOREIGN KEY (appointment_id) REFERENCES appointments (id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_contracts_template
        FOREIGN KEY (template_id) REFERENCES contract_templates (id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =========================
-- Tabla: surveys
-- =========================
CREATE TABLE IF NOT EXISTS surveys (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    appointment_id BIGINT UNSIGNED NOT NULL,
    rating TINYINT UNSIGNED NOT NULL,
    comments TEXT NULL,
    would_recommend BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_surveys_appointment (appointment_id),
    CONSTRAINT fk_surveys_appointment
        FOREIGN KEY (appointment_id) REFERENCES appointments (id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
