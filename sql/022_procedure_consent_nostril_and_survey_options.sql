-- Idempotente: alinea opciones de encuesta (pregunta 3); renombra Nostry→Nostril y DELETE no-op si ya estaba aplicado.
-- Ejecutar si ya tenías datos cargados con la versión anterior de 021/import.

USE cherry_tatto;

UPDATE survey_questions
SET options_json = CAST(
    '["Helix","Lobulos","Expansion Lobulos","Nostril","Surface","Microdermal","Septum","Labio","Ombligo","Pezon","Ceja","Conch","Industrial","Upper Lobe","Tragus","Lengua","Cristina","Daith","Rook","Antihelix","Contrahelix","Flat"]'
    AS JSON
)
WHERE id = 3;

UPDATE procedure_consent_documents
SET survey_option_label = 'Nostril',
    source_filename = 'Nostril.pdf'
WHERE survey_option_label = 'Nostry';

DELETE FROM procedure_consent_documents WHERE survey_option_label = 'Nostry';
