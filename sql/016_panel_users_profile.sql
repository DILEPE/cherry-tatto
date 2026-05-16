-- Perfil extendido para usuarios del panel (nombre, contacto, tienda, rol).
-- Idempotente: cada columna solo se añade si falta.

USE cherry_tatto;

SET @db := DATABASE();

-- first_name AFTER username
SET @c := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'panel_users' AND COLUMN_NAME = 'first_name'
);
SET @sql := IF(
    @c = 0,
    'ALTER TABLE panel_users ADD COLUMN first_name VARCHAR(100) NOT NULL DEFAULT '''' AFTER username',
    'SELECT 1 AS skip_panel_users_first_name'
);
PREPARE _s FROM @sql;
EXECUTE _s;
DEALLOCATE PREPARE _s;

-- last_name AFTER first_name
SET @c := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'panel_users' AND COLUMN_NAME = 'last_name'
);
SET @sql := IF(
    @c = 0,
    'ALTER TABLE panel_users ADD COLUMN last_name VARCHAR(100) NOT NULL DEFAULT '''' AFTER first_name',
    'SELECT 1 AS skip_panel_users_last_name'
);
PREPARE _s FROM @sql;
EXECUTE _s;
DEALLOCATE PREPARE _s;

-- address AFTER last_name
SET @c := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'panel_users' AND COLUMN_NAME = 'address'
);
SET @sql := IF(
    @c = 0,
    'ALTER TABLE panel_users ADD COLUMN address VARCHAR(500) NULL AFTER last_name',
    'SELECT 1 AS skip_panel_users_address'
);
PREPARE _s FROM @sql;
EXECUTE _s;
DEALLOCATE PREPARE _s;

-- phone AFTER address
SET @c := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'panel_users' AND COLUMN_NAME = 'phone'
);
SET @sql := IF(
    @c = 0,
    'ALTER TABLE panel_users ADD COLUMN phone VARCHAR(32) NULL AFTER address',
    'SELECT 1 AS skip_panel_users_phone'
);
PREPARE _s FROM @sql;
EXECUTE _s;
DEALLOCATE PREPARE _s;

-- store AFTER phone
SET @c := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'panel_users' AND COLUMN_NAME = 'store'
);
SET @sql := IF(
    @c = 0,
    'ALTER TABLE panel_users ADD COLUMN store ENUM(''cherry_tattoo'', ''rock_city'') NOT NULL DEFAULT ''cherry_tattoo'' AFTER phone',
    'SELECT 1 AS skip_panel_users_store'
);
PREPARE _s FROM @sql;
EXECUTE _s;
DEALLOCATE PREPARE _s;

-- role AFTER store
SET @c := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'panel_users' AND COLUMN_NAME = 'role'
);
SET @sql := IF(
    @c = 0,
    'ALTER TABLE panel_users ADD COLUMN role ENUM(''administrador'', ''vendedor'', ''perforador'', ''tatuador'') NOT NULL DEFAULT ''vendedor'' AFTER store',
    'SELECT 1 AS skip_panel_users_role'
);
PREPARE _s FROM @sql;
EXECUTE _s;
DEALLOCATE PREPARE _s;
