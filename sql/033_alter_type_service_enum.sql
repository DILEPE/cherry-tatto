-- 033_alter_type_service_enum.sql
-- Alinea reminders.service_type con n8n y la API: piercing | tatuaje
-- (031 usaba tattoo). Ejecutar después de 031/032.

USE cherry_tatto;

ALTER TABLE reminders
  MODIFY COLUMN service_type ENUM('piercing','tatuaje') NOT NULL;
