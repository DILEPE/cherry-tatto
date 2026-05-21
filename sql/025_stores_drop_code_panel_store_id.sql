-- Quita stores.code; panel_users pasa de store (texto/slug) a store_id (FK).
-- Ejecutar después de 024_stores.sql. Idempotente en la medida de lo posible.

USE cherry_tatto;

SET @db := DATABASE();

-- ── panel_users.store_id ─────────────────────────────────────────────
SET @has_store_id := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'panel_users' AND COLUMN_NAME = 'store_id'
);

SET @sql_add_sid := IF(
    @has_store_id = 0,
    'ALTER TABLE panel_users ADD COLUMN store_id BIGINT UNSIGNED NULL AFTER phone',
    'SELECT 1 AS skip_panel_users_store_id'
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

-- Migrar slug/código → id (cuando existen stores.code y panel_users.store)
-- WHERE pu.id > 0: compatible con MySQL Workbench «safe updates» (usa la PK).
SET @sql_mig := IF(
    @has_store_col > 0 AND @has_stores_code > 0,
    'UPDATE panel_users pu INNER JOIN stores s ON pu.store = s.code SET pu.store_id = s.id WHERE pu.store_id IS NULL AND pu.id > 0',
    'SELECT 1 AS skip_mig_store_code'
);
PREPARE _s2 FROM @sql_mig;
EXECUTE _s2;
DEALLOCATE PREPARE _s2;

-- Migrar ENUM/VARCHAR legacy (cherry_tattoo, rock_city) por nombre de tienda
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

SET @sql_sid_notnull := IF(
    @has_store_id = 0 OR (SELECT COUNT(*) FROM panel_users WHERE store_id IS NULL) = 0,
    'ALTER TABLE panel_users MODIFY COLUMN store_id BIGINT UNSIGNED NOT NULL',
    'SELECT 1 AS skip_store_id_notnull_pending_nulls'
);
PREPARE _s3 FROM @sql_sid_notnull;
EXECUTE _s3;
DEALLOCATE PREPARE _s3;

SET @sql_drop_store := IF(
    @has_store_col > 0,
    'ALTER TABLE panel_users DROP COLUMN store',
    'SELECT 1 AS skip_drop_panel_users_store'
);
PREPARE _s4 FROM @sql_drop_store;
EXECUTE _s4;
DEALLOCATE PREPARE _s4;

SET @fk_exists := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = @db
      AND TABLE_NAME = 'panel_users'
      AND CONSTRAINT_NAME = 'fk_panel_users_store'
);

SET @sql_fk := IF(
    @fk_exists = 0,
    'ALTER TABLE panel_users ADD CONSTRAINT fk_panel_users_store FOREIGN KEY (store_id) REFERENCES stores (id)',
    'SELECT 1 AS skip_fk_panel_users_store'
);
PREPARE _s5 FROM @sql_fk;
EXECUTE _s5;
DEALLOCATE PREPARE _s5;

-- ── stores: eliminar code ────────────────────────────────────────────
SET @sql_drop_uk := IF(
    @has_stores_code > 0,
    'ALTER TABLE stores DROP INDEX uk_stores_code',
    'SELECT 1 AS skip_drop_uk_stores_code'
);
PREPARE _s6 FROM @sql_drop_uk;
EXECUTE _s6;
DEALLOCATE PREPARE _s6;

SET @sql_drop_code := IF(
    @has_stores_code > 0,
    'ALTER TABLE stores DROP COLUMN code',
    'SELECT 1 AS skip_drop_stores_code'
);
PREPARE _s7 FROM @sql_drop_code;
EXECUTE _s7;
DEALLOCATE PREPARE _s7;
