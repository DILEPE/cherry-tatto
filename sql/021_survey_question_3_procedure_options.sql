-- Opciones de la pregunta id=3: títulos de los consentimientos (sin extensión .pdf).
-- Idempotente: UPDATE por id=3 (mismo resultado si se repite).
-- «Tatuaje» no va en el cuestionario; el PDF de tatuaje se envía por tipo de cita.
-- Ajusta question_type a select si la pregunta 3 no era de opciones.

USE cherry_tatto;

-- Texto JSON válido (sin CAST AS JSON: compatible si la columna es LONGTEXT o servidor sin tipo JSON).
UPDATE survey_questions
SET options_json = '["Helix","Lobulos","Expansion Lobulos","Nostril","Surface","Microdermal","Septum","Labio","Ombligo","Pezon","Ceja","Conch","Industrial","Upper Lobe","Tragus","Lengua","Cristina","Daith","Rook","Antihelix","Contrahelix","Flat"]'
WHERE id = 3;
