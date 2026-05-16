-- Customer management + link to appointments (MySQL 8+, InnoDB)
-- Índice uk_customers_email con prefijo por límite InnoDB 767 bytes con utf8mb4 (error 1071).
--
-- Idempotente: se puede ejecutar varias veces (columna customer_id, FK e índices ya existentes no fallan).

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
    social_media VARCHAR(50) NULL,
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
    UNIQUE KEY uk_customers_email (email(191)),
    CONSTRAINT chk_customers_minor_guardian CHECK (
        is_minor = FALSE
        OR (
            guardian_name IS NOT NULL
            AND guardian_document_type IS NOT NULL
            AND guardian_document_number IS NOT NULL
        )
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- appointments.customer_id (solo si no existe)
SET @db := DATABASE();
SET @has_customer_id := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @db
      AND TABLE_NAME = 'appointments'
      AND COLUMN_NAME = 'customer_id'
);
SET @sql_add_customer_id := IF(
    @has_customer_id = 0,
    'ALTER TABLE appointments ADD COLUMN customer_id BIGINT UNSIGNED NULL',
    'SELECT 1 AS skip_customer_id_column'
);
PREPARE _stmt_customer_id FROM @sql_add_customer_id;
EXECUTE _stmt_customer_id;
DEALLOCATE PREPARE _stmt_customer_id;

-- FK solo si no existe (nombre fijo fk_appointments_customer)
SET @has_fk := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = @db
      AND TABLE_NAME = 'appointments'
      AND CONSTRAINT_NAME = 'fk_appointments_customer'
      AND CONSTRAINT_TYPE = 'FOREIGN KEY'
);
SET @sql_fk := IF(
    @has_fk = 0,
    'ALTER TABLE appointments ADD CONSTRAINT fk_appointments_customer FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE SET NULL ON UPDATE CASCADE',
    'SELECT 1 AS skip_fk_appointments_customer'
);
PREPARE _stmt_fk FROM @sql_fk;
EXECUTE _stmt_fk;
DEALLOCATE PREPARE _stmt_fk;

-- Índices auxiliares en customers (solo si no existen)
SET @has_idx_name := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = @db
      AND TABLE_NAME = 'customers'
      AND INDEX_NAME = 'idx_customers_name'
);
SET @sql_idx_name := IF(
    @has_idx_name = 0,
    'CREATE INDEX idx_customers_name ON customers (last_name, first_name)',
    'SELECT 1 AS skip_idx_customers_name'
);
PREPARE _stmt_idx_name FROM @sql_idx_name;
EXECUTE _stmt_idx_name;
DEALLOCATE PREPARE _stmt_idx_name;

SET @has_idx_deleted := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = @db
      AND TABLE_NAME = 'customers'
      AND INDEX_NAME = 'idx_customers_deleted'
);
SET @sql_idx_deleted := IF(
    @has_idx_deleted = 0,
    'CREATE INDEX idx_customers_deleted ON customers (deleted_at)',
    'SELECT 1 AS skip_idx_customers_deleted'
);
PREPARE _stmt_idx_deleted FROM @sql_idx_deleted;
EXECUTE _stmt_idx_deleted;
DEALLOCATE PREPARE _stmt_idx_deleted;
