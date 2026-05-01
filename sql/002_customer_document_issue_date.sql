-- Fecha de expedición del documento de identidad del cliente (no del tutor).
-- Ejecutar una vez; si la columna ya existe, omitir o comentar.

ALTER TABLE customers
    ADD COLUMN document_issue_date DATE NULL
    AFTER document_number;
