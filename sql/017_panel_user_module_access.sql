-- Permisos por módulo del panel (usuarios que no son administrador).
-- Idempotente: CREATE TABLE IF NOT EXISTS.

USE cherry_tatto;

CREATE TABLE IF NOT EXISTS panel_user_module_access (
    user_id BIGINT UNSIGNED NOT NULL,
    module_key VARCHAR(32) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, module_key),
    CONSTRAINT fk_panel_user_module_user
        FOREIGN KEY (user_id) REFERENCES panel_users (id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
