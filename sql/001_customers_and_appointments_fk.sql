-- Customer management + link to appointments (MySQL 8+, InnoDB)
-- Review before apply: if `customer_id` already exists, skip the ALTER ADD COLUMN.

CREATE TABLE IF NOT EXISTS customers (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    birth_date DATE NOT NULL,
    document_type ENUM('CC', 'TI', 'CE', 'PAS') NOT NULL,
    document_number VARCHAR(32) NOT NULL,
    document_issue_date DATE NULL,
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
    UNIQUE KEY uk_customers_email (email),
    CONSTRAINT chk_customers_minor_guardian CHECK (
        is_minor = FALSE
        OR (
            guardian_name IS NOT NULL
            AND guardian_document_type IS NOT NULL
            AND guardian_document_number IS NOT NULL
        )
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Add FK column (run once). If column exists, comment this line out:
ALTER TABLE appointments ADD COLUMN customer_id BIGINT UNSIGNED NULL;

ALTER TABLE appointments
    ADD CONSTRAINT fk_appointments_customer
    FOREIGN KEY (customer_id) REFERENCES customers (id)
    ON DELETE SET NULL ON UPDATE CASCADE;

CREATE INDEX idx_customers_name ON customers (last_name, first_name);
CREATE INDEX idx_customers_deleted ON customers (deleted_at);
