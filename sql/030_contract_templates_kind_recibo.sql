-- Comentario de columna: contract_templates admite tipo recibo (órdenes/abonos).
-- Idempotente. No hay CHECK en contract_kind: solo documenta el valor permitido.

USE cherry_tatto;

SET @db := DATABASE();

SET @sql := (
    SELECT CONCAT(
        'ALTER TABLE contract_templates MODIFY COLUMN contract_kind VARCHAR(20) NOT NULL DEFAULT ''tattoo'' ',
        'COMMENT ''tattoo | piercing | recibo'''
    )
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @db
      AND TABLE_NAME = 'contract_templates'
      AND COLUMN_NAME = 'contract_kind'
    LIMIT 1
);

SET @sql := IFNULL(@sql, 'SELECT 1 AS skip_contract_kind_comment');
PREPARE _s FROM @sql;
EXECUTE _s;
DEALLOCATE PREPARE _s;
