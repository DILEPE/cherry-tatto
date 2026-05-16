-- Preguntas configurables de encuesta y respuestas por envío (survey).
-- Orden: tras 010_contract_templates_contract_kind.sql
-- Idempotente: CREATE TABLE IF NOT EXISTS; MODIFY surveys.id puede repetirse.
--
-- options_json: LONGTEXT (JSON como texto), compatible con MySQL sin tipo JSON nativo (error 1064).
--
-- Si al crear survey_answers obtienes el error 3780 (columnas incompatibles en FK),
-- suele ser porque surveys.id no coincide en signo/tipo con este repo (000_initial usa
-- BIGINT UNSIGNED). El ALTER siguiente alinea surveys.id antes del CREATE de respuestas.

USE cherry_tatto;

CREATE TABLE IF NOT EXISTS survey_questions (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    label VARCHAR(500) NOT NULL,
    question_type VARCHAR(32) NOT NULL COMMENT 'rating_1_5 | yes_no | text | radio | checkbox | select | textarea | text_short | number',
    options_json LONGTEXT NULL COMMENT 'Opciones (array JSON como texto) para radio, checkbox, select',
    sort_order INT NOT NULL DEFAULT 0,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT chk_survey_questions_type CHECK (
        question_type IN (
            'rating_1_5', 'yes_no', 'text',
            'radio', 'checkbox', 'select',
            'textarea', 'text_short', 'number'
        )
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Alinear PK de surveys con BIGINT UNSIGNED (como en 000_initial_schema_cherry_tatto.sql)
ALTER TABLE surveys
    MODIFY COLUMN id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT;

CREATE TABLE IF NOT EXISTS survey_answers (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    survey_id BIGINT UNSIGNED NOT NULL,
    question_id BIGINT UNSIGNED NOT NULL,
    answer_rating TINYINT UNSIGNED NULL,
    answer_bool TINYINT(1) NULL,
    answer_text TEXT NULL,
    answer_number DECIMAL(14,4) NULL COMMENT 'Valor numérico (pregunta tipo number)',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_survey_answers_survey_question (survey_id, question_id),
    CONSTRAINT fk_survey_answers_survey
        FOREIGN KEY (survey_id) REFERENCES surveys (id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_survey_answers_question
        FOREIGN KEY (question_id) REFERENCES survey_questions (id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
