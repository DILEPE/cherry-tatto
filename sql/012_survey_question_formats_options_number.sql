-- Ampliación: formatos radio, checkbox, select, textarea, texto corto, numérico.
-- Columna options_json como LONGTEXT (JSON serializado); answer_number en respuestas.
-- Idempotente: columnas y CHECK solo se aplican si faltan / hace falta reemplazar.

USE cherry_tatto;

SET @db := DATABASE();

-- options_json en survey_questions (texto JSON; sin tipo JSON nativo en el servidor)
SET @c := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @db
      AND TABLE_NAME = 'survey_questions'
      AND COLUMN_NAME = 'options_json'
);
SET @sql := IF(
    @c = 0,
    'ALTER TABLE survey_questions ADD COLUMN options_json LONGTEXT NULL COMMENT ''Opciones (array JSON como texto) para radio, checkbox, select'' AFTER question_type',
    'SELECT 1 AS skip_options_json'
);
PREPARE _s FROM @sql;
EXECUTE _s;
DEALLOCATE PREPARE _s;

-- answer_number en survey_answers
SET @c := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @db
      AND TABLE_NAME = 'survey_answers'
      AND COLUMN_NAME = 'answer_number'
);
SET @sql := IF(
    @c = 0,
    'ALTER TABLE survey_answers ADD COLUMN answer_number DECIMAL(14,4) NULL COMMENT ''Respuesta numérica (pregunta tipo number)'' AFTER answer_text',
    'SELECT 1 AS skip_answer_number'
);
PREPARE _s FROM @sql;
EXECUTE _s;
DEALLOCATE PREPARE _s;

-- Sustituir CHECK chk_survey_questions_type por uno que incluye los nuevos question_type
SET @has_chk_type := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = @db
      AND TABLE_NAME = 'survey_questions'
      AND CONSTRAINT_NAME = 'chk_survey_questions_type'
      AND CONSTRAINT_TYPE = 'CHECK'
);

SET @sql := IF(
    @has_chk_type > 0,
    'ALTER TABLE survey_questions DROP CHECK chk_survey_questions_type',
    'SELECT 1 AS skip_drop_chk_survey_questions_type'
);
PREPARE _s FROM @sql;
EXECUTE _s;
DEALLOCATE PREPARE _s;

SET @has_chk_type_after := (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = @db
      AND TABLE_NAME = 'survey_questions'
      AND CONSTRAINT_NAME = 'chk_survey_questions_type'
      AND CONSTRAINT_TYPE = 'CHECK'
);

SET @sql := IF(
    @has_chk_type_after = 0,
    'ALTER TABLE survey_questions ADD CONSTRAINT chk_survey_questions_type CHECK (
        question_type IN (
            ''rating_1_5'', ''yes_no'', ''text'',
            ''radio'', ''checkbox'', ''select'',
            ''textarea'', ''text_short'', ''number''
        )
    )',
    'SELECT 1 AS skip_add_chk_survey_questions_type'
);
PREPARE _s FROM @sql;
EXECUTE _s;
DEALLOCATE PREPARE _s;
