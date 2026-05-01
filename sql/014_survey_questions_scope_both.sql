-- Ampliar ámbito de preguntas de encuesta: valor **both** (tatuaje y piercing).
-- Orden: tras 013_survey_questions_contract_kind.sql (si ya aplicaste 013 solo con tattoo/piercing).

USE cherry_tatto;

ALTER TABLE survey_questions
    DROP CHECK chk_survey_questions_contract_kind;

ALTER TABLE survey_questions
    ADD CONSTRAINT chk_survey_questions_contract_kind
        CHECK (contract_kind IN ('tattoo', 'piercing', 'both'));
