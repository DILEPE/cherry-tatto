-- Preguntas de encuesta: ámbito tatuaje vs piercing (misma convención que contract_templates).
-- Orden: tras 012_survey_question_formats_options_number.sql
-- Idempotente.

USE cherry_tatto;

SET @db := DATABASE();

SET @has_contract_kind := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @db
      AND TABLE_NAME = 'survey_questions'
      AND COLUMN_NAME = 'contract_kind'
);

SET @sql := IF(
    @has_contract_kind = 0,
    'ALTER TABLE survey_questions ADD COLUMN contract_kind VARCHAR(16) NOT NULL DEFAULT ''tattoo'' COMMENT ''tattoo | piercing | both'' AFTER sort_order',
    'SELECT 1 AS skip_survey_questions_contract_kind_column'
);
PREPARE _s FROM @sql;
EXECUTE _s;
DEALLOCATE PREPARE _s;

SET @has_chk_ck := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = @db
      AND TABLE_NAME = 'survey_questions'
      AND CONSTRAINT_NAME = 'chk_survey_questions_contract_kind'
      AND CONSTRAINT_TYPE = 'CHECK'
);

SET @sql := IF(
    @has_chk_ck = 0,
    'ALTER TABLE survey_questions ADD CONSTRAINT chk_survey_questions_contract_kind CHECK (contract_kind IN (''tattoo'', ''piercing'', ''both''))',
    'SELECT 1 AS skip_chk_survey_questions_contract_kind'
);
PREPARE _s FROM @sql;
EXECUTE _s;
DEALLOCATE PREPARE _s;
