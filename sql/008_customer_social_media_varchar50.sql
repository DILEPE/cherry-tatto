-- social_media: columna texto plano (50 caracteres), sin JSON.
-- Ejecutar sobre la base del proyecto (p. ej. cherry_tatto).

USE cherry_tatto;

-- Workbench activa sql_safe_updates y bloquea UPDATE masivos aunque la tabla tenga PK.
-- Esta migración es intencional: se desactiva solo durante este bloque y se restaura el valor previo.
SET @__prev_safe_updates := @@SESSION.sql_safe_updates;
SET SESSION sql_safe_updates = 0;

UPDATE customers
SET social_media = LEFT(CAST(social_media AS CHAR(500)), 50)
WHERE social_media IS NOT NULL;

SET SESSION sql_safe_updates = @__prev_safe_updates;

ALTER TABLE customers
    MODIFY COLUMN social_media VARCHAR(50) NULL
    COMMENT 'Redes / contacto, texto plano';
