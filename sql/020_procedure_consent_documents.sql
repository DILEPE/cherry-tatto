-- Documentos PDF de consentimiento por tipo de procedimiento (opción de encuesta → PDF en base64).
-- Orden: tras migraciones de encuestas (011+).
-- Idempotente: CREATE TABLE IF NOT EXISTS.
--
-- PK sobre etiqueta: VARCHAR(191) para InnoDB con límite clásico 767 bytes y utf8mb4 (error 1071 con VARCHAR(255)).

USE cherry_tatto;

CREATE TABLE IF NOT EXISTS procedure_consent_documents (
    survey_option_label VARCHAR(191) NOT NULL COMMENT 'Texto exacto de la opción (coincide con survey_answers.answer_text)',
    source_filename VARCHAR(255) NOT NULL COMMENT 'Nombre sugerido del archivo PDF',
    pdf_base64 LONGTEXT NOT NULL COMMENT 'PDF codificado en Base64 estándar',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (survey_option_label)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
