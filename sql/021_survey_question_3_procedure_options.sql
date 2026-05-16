-- Opciones de la pregunta id=3: títulos de los consentimientos (sin extensión .pdf).
-- «Tatuaje» no va en el cuestionario; el PDF de tatuaje se envía por tipo de cita.
-- Ajusta question_type a select si la pregunta 3 no era de opciones.

USE cherry_tatto;

UPDATE survey_questions
SET options_json = CAST(
    '["Helix","Lobulos","Expansion Lobulos","Nostril","Surface","Microdermal","Septum","Labio","Ombligo","Pezon","Ceja","Conch","Industrial","Upper Lobe","Tragus","Lengua","Cristina","Daith","Rook","Antihelix","Contrahelix","Flat"]'
    AS JSON
)
WHERE id = 3;
