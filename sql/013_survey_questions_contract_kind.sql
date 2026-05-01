-- Preguntas de encuesta: ámbito tatuaje vs piercing (misma convención que contract_templates).
-- Orden: tras 012_survey_question_formats_options_number.sql

USE cherry_tatto;

ALTER TABLE survey_questions
    ADD COLUMN contract_kind VARCHAR(16) NOT NULL DEFAULT 'tattoo'
        COMMENT 'tattoo | piercing | both'
        AFTER sort_order,
    ADD CONSTRAINT chk_survey_questions_contract_kind
        CHECK (contract_kind IN ('tattoo', 'piercing', 'both'));
