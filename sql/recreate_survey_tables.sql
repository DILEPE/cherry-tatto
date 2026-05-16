-- Recreación de tablas de encuestas (uso tras DROP manual o pérdida de estructura).
-- BORRA cualquier dato previo en: survey_answers, survey_questions, surveys.
-- Requiere que exista la tabla appointments (FK appointment_id → appointments.id).

USE cherry_tatto;

SET @prev_fk := @@FOREIGN_KEY_CHECKS;
SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS survey_answers;
DROP TABLE IF EXISTS survey_questions;
DROP TABLE IF EXISTS surveys;

-- ═══════════════════════════════════════════════════════════════════════════
-- Alinear appointments.id a BIGINT UNSIGNED (MySQL 8 error 3780).
-- Hay que quitar antes las FK hijas (p. ej. contracts_ibfk_1), modificar columnas
-- y volver a crear las FK como en 000_initial / 006.
-- ═══════════════════════════════════════════════════════════════════════════

-- Quitar FK contracts → appointments (nombre autogenerado o fk_contracts_appointment)
SET @fk_name := (
    SELECT CONSTRAINT_NAME
    FROM information_schema.referential_constraints
    WHERE constraint_schema = DATABASE()
      AND table_name = 'contracts'
      AND referenced_table_name = 'appointments'
    LIMIT 1
);
SET @drop_contracts_fk := IF(
    @fk_name IS NOT NULL,
    CONCAT('ALTER TABLE contracts DROP FOREIGN KEY `', @fk_name, '`'),
    'SELECT 1 AS _skip_contracts_fk'
);
PREPARE _dc FROM @drop_contracts_fk;
EXECUTE _dc;
DEALLOCATE PREPARE _dc;

-- Quitar FK appointment_payments → appointments (si la tabla existe)
SET @fk_pay := (
    SELECT CONSTRAINT_NAME
    FROM information_schema.referential_constraints
    WHERE constraint_schema = DATABASE()
      AND table_name = 'appointment_payments'
      AND referenced_table_name = 'appointments'
    LIMIT 1
);
SET @drop_pay_fk := IF(
    @fk_pay IS NOT NULL,
    CONCAT('ALTER TABLE appointment_payments DROP FOREIGN KEY `', @fk_pay, '`'),
    'SELECT 1 AS _skip_pay_fk'
);
PREPARE _dp FROM @drop_pay_fk;
EXECUTE _dp;
DEALLOCATE PREPARE _dp;

ALTER TABLE contracts
    MODIFY COLUMN appointment_id BIGINT UNSIGNED NOT NULL;

SET @has_payments := (
    SELECT COUNT(*)
    FROM information_schema.tables
    WHERE table_schema = DATABASE()
      AND table_name = 'appointment_payments'
);
SET @mod_pay := IF(
    @has_payments > 0,
    'ALTER TABLE appointment_payments MODIFY COLUMN appointment_id BIGINT UNSIGNED NOT NULL',
    'SELECT 1 AS _skip_mod_pay'
);
PREPARE _mp FROM @mod_pay;
EXECUTE _mp;
DEALLOCATE PREPARE _mp;

ALTER TABLE appointments
    MODIFY COLUMN id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT;

ALTER TABLE contracts
    ADD CONSTRAINT fk_contracts_appointment
        FOREIGN KEY (appointment_id) REFERENCES appointments (id)
        ON DELETE CASCADE ON UPDATE CASCADE;

SET @add_pay_fk := IF(
    @has_payments > 0,
    'ALTER TABLE appointment_payments ADD CONSTRAINT fk_appointment_payments_appointment FOREIGN KEY (appointment_id) REFERENCES appointments (id) ON DELETE CASCADE ON UPDATE CASCADE',
    'SELECT 1 AS _skip_add_pay_fk'
);
PREPARE _ap FROM @add_pay_fk;
EXECUTE _ap;
DEALLOCATE PREPARE _ap;

-- ═══════════════════════════════════════════════════════════════════════════
-- Tablas de encuesta
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE surveys (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    appointment_id BIGINT UNSIGNED NOT NULL,
    rating TINYINT UNSIGNED NOT NULL,
    comments TEXT NULL,
    would_recommend BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_surveys_appointment (appointment_id),
    CONSTRAINT fk_surveys_appointment
        FOREIGN KEY (appointment_id) REFERENCES appointments (id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE survey_questions (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    label VARCHAR(500) NOT NULL,
    question_type VARCHAR(32) NOT NULL COMMENT 'rating_1_5 | yes_no | text | radio | checkbox | select | textarea | text_short | number',
    options_json LONGTEXT NULL COMMENT 'Opciones (array JSON como texto) para radio, checkbox, select',
    sort_order INT NOT NULL DEFAULT 0,
    contract_kind VARCHAR(16) NOT NULL DEFAULT 'tattoo' COMMENT 'tattoo | piercing | both',
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT chk_survey_questions_type CHECK (
        question_type IN (
            'rating_1_5', 'yes_no', 'text',
            'radio', 'checkbox', 'select',
            'textarea', 'text_short', 'number'
        )
    ),
    CONSTRAINT chk_survey_questions_contract_kind CHECK (contract_kind IN ('tattoo', 'piercing', 'both'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE survey_answers (
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

SET FOREIGN_KEY_CHECKS = @prev_fk;
