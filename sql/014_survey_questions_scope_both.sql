-- Ampliar ámbito de preguntas de encuesta: valor **both** (tatuaje y piercing).
-- Orden: tras 013_survey_questions_contract_kind.sql
-- Idempotente: reemplaza el CHECK solo si existe la versión anterior o falta el nuevo.

USE cherry_tatto;

SET @db := DATABASE();

SET @has_chk_ck := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = @db
      AND TABLE_NAME = 'survey_questions'
      AND CONSTRAINT_NAME = 'chk_survey_questions_contract_kind'
      AND CONSTRAINT_TYPE = 'CHECK'
);

SET @sql := IF(
    @has_chk_ck > 0,
    'ALTER TABLE survey_questions DROP CHECK chk_survey_questions_contract_kind',
    'SELECT 1 AS skip_drop_chk_survey_questions_contract_kind'
);
PREPARE _s FROM @sql;
EXECUTE _s;
DEALLOCATE PREPARE _s;

SET @need_add_chk := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = @db
      AND TABLE_NAME = 'survey_questions'
      AND CONSTRAINT_NAME = 'chk_survey_questions_contract_kind'
      AND CONSTRAINT_TYPE = 'CHECK'
);

SET @sql := IF(
    @need_add_chk = 0,
    'ALTER TABLE survey_questions ADD CONSTRAINT chk_survey_questions_contract_kind CHECK (contract_kind IN (''tattoo'', ''piercing'', ''both''))',
    'SELECT 1 AS skip_add_chk_survey_questions_contract_kind_014'
);
PREPARE _s FROM @sql;
EXECUTE _s;
DEALLOCATE PREPARE _s;
