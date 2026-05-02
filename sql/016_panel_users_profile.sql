-- Perfil extendido para usuarios del panel (nombre, contacto, tienda, rol).

USE cherry_tatto;

ALTER TABLE panel_users
    ADD COLUMN first_name VARCHAR(100) NOT NULL DEFAULT '' AFTER username,
    ADD COLUMN last_name VARCHAR(100) NOT NULL DEFAULT '' AFTER first_name,
    ADD COLUMN address VARCHAR(500) NULL AFTER last_name,
    ADD COLUMN phone VARCHAR(32) NULL AFTER address,
    ADD COLUMN store ENUM('cherry_tattoo', 'rock_city') NOT NULL DEFAULT 'cherry_tattoo' AFTER phone,
    ADD COLUMN role ENUM('administrador', 'vendedor', 'perforador', 'tatuador') NOT NULL DEFAULT 'vendedor' AFTER store;
