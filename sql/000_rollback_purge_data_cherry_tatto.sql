-- Rollback de datos: elimina TODA la data del esquema cherry_tatto
-- No elimina estructura (tablas/columnas), solo registros.

USE cherry_tatto;

SET @prev_fk_checks := @@FOREIGN_KEY_CHECKS;
SET FOREIGN_KEY_CHECKS = 0;

TRUNCATE TABLE survey_answers;
TRUNCATE TABLE surveys;
TRUNCATE TABLE survey_questions;
TRUNCATE TABLE contracts;
TRUNCATE TABLE appointments;
TRUNCATE TABLE contract_templates;
TRUNCATE TABLE customers;

SET FOREIGN_KEY_CHECKS = @prev_fk_checks;
