-- 032_add_control_label_to_reminders.sql
USE cherry_tatto;

ALTER TABLE reminders
  ADD COLUMN control_label VARCHAR(50) NOT NULL DEFAULT ''
    COMMENT 'etiqueta del control para parámetro WhatsApp'
    AFTER reminder_date;