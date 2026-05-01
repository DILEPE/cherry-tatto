-- Campos adicionales para firma de contrato digital con evidencia de tutor.
-- Ejecutar una vez en bases existentes.

ALTER TABLE contracts
    ADD COLUMN artist_signature LONGTEXT NULL AFTER tutor_signature,
    ADD COLUMN tutor_document_front LONGTEXT NULL AFTER artist_signature,
    ADD COLUMN tutor_document_back LONGTEXT NULL AFTER tutor_document_front,
    ADD COLUMN contract_text LONGTEXT NULL AFTER tutor_document_back;

