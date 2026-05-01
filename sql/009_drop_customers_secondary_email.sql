-- Elimina el correo secundario del cliente (ya no se usa en API ni formularios).
-- Ejecutar sobre la base del proyecto (p. ej. cherry_tatto).

USE cherry_tatto;

ALTER TABLE customers DROP COLUMN secondary_email;
