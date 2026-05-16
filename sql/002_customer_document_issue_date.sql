-- Fecha de expedición del documento de identidad del cliente (no del tutor).
-- Idempotente: solo añade la columna si no existe.

SET @db := DATABASE();

SET @has_doc_issue := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @db
      AND TABLE_NAME = 'customers'
      AND COLUMN_NAME = 'document_issue_date'
);

SET @sql_doc_issue := IF(
    @has_doc_issue = 0,
    'ALTER TABLE customers ADD COLUMN document_issue_date DATE NULL AFTER document_number',
    'SELECT 1 AS skip_document_issue_date'
);

PREPARE _stmt_doc_issue FROM @sql_doc_issue;
EXECUTE _stmt_doc_issue;
DEALLOCATE PREPARE _stmt_doc_issue;
