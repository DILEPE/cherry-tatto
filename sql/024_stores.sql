-- Catálogo de tiendas y panel_users.store_id (sin slug «code»).
-- Orden: tras 023_appointment_payment_paid_on.sql
--
-- En MySQL Workbench: ejecuta con la base seleccionada, o deja USE cherry_tatto;
-- (ajusta el nombre si tu esquema es otro, p. ej. el de DB_NAME en .env).

USE cherry_tatto;

CREATE TABLE IF NOT EXISTS stores (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    name VARCHAR(200) NOT NULL,
    address VARCHAR(500) NULL,
    phone VARCHAR(40) NULL,
    email VARCHAR(120) NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP NULL DEFAULT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO stores (name, is_active)
SELECT 'Cherry Tattoo', 1
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM stores WHERE name = 'Cherry Tattoo' AND deleted_at IS NULL);

INSERT INTO stores (name, is_active)
SELECT 'Rock City', 1
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM stores WHERE name = 'Rock City' AND deleted_at IS NULL);

-- panel_users: store_id en lugar de ENUM/VARCHAR store (si aún no existe store_id)
SET @db := DATABASE();

SET @has_store_id := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'panel_users' AND COLUMN_NAME = 'store_id'
);

SET @sql_add_sid := IF(
    @has_store_id = 0,
    'ALTER TABLE panel_users ADD COLUMN store_id BIGINT UNSIGNED NULL AFTER phone',
    'SELECT 1 AS skip_panel_users_store_id_024'
);
PREPARE _s1 FROM @sql_add_sid;
EXECUTE _s1;
DEALLOCATE PREPARE _s1;

SET @has_store_col := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'panel_users' AND COLUMN_NAME = 'store'
);

SET @has_stores_code := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'stores' AND COLUMN_NAME = 'code'
);

SET @sql_mig_code := IF(
    @has_store_col > 0 AND @has_stores_code > 0,
    'UPDATE panel_users pu INNER JOIN stores s ON pu.store = s.code SET pu.store_id = s.id WHERE pu.store_id IS NULL AND pu.id > 0',
    'SELECT 1 AS skip_mig_024'
);
PREPARE _s2 FROM @sql_mig_code;
EXECUTE _s2;
DEALLOCATE PREPARE _s2;

UPDATE panel_users pu
INNER JOIN stores s ON s.name = 'Cherry Tattoo' AND s.deleted_at IS NULL
SET pu.store_id = s.id
WHERE pu.id > 0 AND pu.store_id IS NULL AND pu.store IN ('cherry_tattoo', 'Cherry Tattoo');

UPDATE panel_users pu
INNER JOIN stores s ON s.name = 'Rock City' AND s.deleted_at IS NULL
SET pu.store_id = s.id
WHERE pu.id > 0 AND pu.store_id IS NULL AND pu.store IN ('rock_city', 'Rock City');

UPDATE panel_users
SET store_id = (SELECT MIN(id) FROM stores WHERE deleted_at IS NULL LIMIT 1)
WHERE id > 0 AND store_id IS NULL;

SET @sql_enum_varchar := IF(
    @has_store_col > 0,
    'ALTER TABLE panel_users DROP COLUMN store',
    'SELECT 1 AS skip_drop_store_024'
);
PREPARE _s3 FROM @sql_enum_varchar;
EXECUTE _s3;
DEALLOCATE PREPARE _s3;

SET @sql_drop_uk := IF(
    @has_stores_code > 0,
    'ALTER TABLE stores DROP INDEX uk_stores_code',
    'SELECT 1 AS skip_drop_uk_024'
);
PREPARE _s4 FROM @sql_drop_uk;
EXECUTE _s4;
DEALLOCATE PREPARE _s4;

SET @sql_drop_code := IF(
    @has_stores_code > 0,
    'ALTER TABLE stores DROP COLUMN code',
    'SELECT 1 AS skip_drop_code_024'
);
PREPARE _s5 FROM @sql_drop_code;
EXECUTE _s5;
DEALLOCATE PREPARE _s5;

SET @sql_sid_nn := IF(
    (SELECT COUNT(*) FROM panel_users WHERE store_id IS NULL) = 0,
    'ALTER TABLE panel_users MODIFY COLUMN store_id BIGINT UNSIGNED NOT NULL',
    'SELECT 1 AS skip_store_id_nn_024'
);
PREPARE _s6 FROM @sql_sid_nn;
EXECUTE _s6;
DEALLOCATE PREPARE _s6;

SET @fk_exists := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = @db
      AND TABLE_NAME = 'panel_users'
      AND CONSTRAINT_NAME = 'fk_panel_users_store'
);

SET @sql_fk := IF(
    @fk_exists = 0,
    'ALTER TABLE panel_users ADD CONSTRAINT fk_panel_users_store FOREIGN KEY (store_id) REFERENCES stores (id)',
    'SELECT 1 AS skip_fk_024'
);
PREPARE _s7 FROM @sql_fk;
EXECUTE _s7;
DEALLOCATE PREPARE _s7;
