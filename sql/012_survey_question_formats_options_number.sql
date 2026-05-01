-- Ampliación: formatos radio, checkbox, select, textarea, texto corto, numérico.
-- Opciones JSON para choice types; columna answer_number en respuestas.
-- Ejecutar si ya aplicaste una versión anterior de 011 sin estas columnas.
-- Si instalas desde el 011 actualizado del repo, este script puede fallar en ALTER duplicado: ignora o comenta bloques ya aplicados.

USE cherry_tatto;

ALTER TABLE survey_questions
    ADD COLUMN options_json JSON NULL COMMENT 'Opciones (array de strings) para radio, checkbox, select' AFTER question_type;

ALTER TABLE survey_answers
    ADD COLUMN answer_number DECIMAL(14,4) NULL COMMENT 'Respuesta numérica (pregunta tipo number)' AFTER answer_text;

-- Sustituye el CHECK por uno que incluya los nuevos question_type
ALTER TABLE survey_questions DROP CHECK chk_survey_questions_type;

ALTER TABLE survey_questions
    ADD CONSTRAINT chk_survey_questions_type CHECK (
        question_type IN (
            'rating_1_5', 'yes_no', 'text',
            'radio', 'checkbox', 'select',
            'textarea', 'text_short', 'number'
        )
    );
