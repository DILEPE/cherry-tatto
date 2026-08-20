-- =============================================================================
-- Importación one-shot: rcs_appointment.client → cherry_tatto.customers
-- =============================================================================
-- No es una migración de esquema. Ejecutar a mano (idempotente por
-- document_number: no duplica clientes que ya existan en cherry_tatto).
-- Sin CTE (WITH): usa tablas derivadas y una tabla auxiliar, compatible con
-- MySQL 5.7+ / 8 / 9 y con MySQL Workbench.
--
-- Origen (rcs_appointment.client):
--   id, first_name, last_name, document, document_type, email, celphone,
--   birth_date, address, created_user, created_date, updated_user,
--   updated_date, new_client
--
-- Destino (cherry_tatto.customers): id nuevo (AUTO_INCREMENT).
--   _import_rcs_client_map guarda rcs_client_id → cherry customer_id
--   por si más adelante se migran citas u otras tablas.
--
-- Campos de origen sin equivalente se omiten (created_user, updated_user,
-- new_client). Tutor, redes, nacionalidad, etc. quedan NULL.
--
-- Mismo host MySQL, dos bases, dos usuarios
-- -----------------------------------------------------------------------------
-- El INSERT ... SELECT cruzado solo funciona si la sesión actual puede
-- LEER rcs_appointment.client e INSERTAR en cherry_tatto.customers.
--
-- Opción A (recomendada): conectar como root / DBA y ejecutar este archivo.
--
-- Opción B: conceder lectura al usuario de cherry_tatto (conectar como root):
--
--   GRANT SELECT ON rcs_appointment.client TO 'USUARIO_CHERRY'@'%';
--   FLUSH PRIVILEGES;
--
--   Luego conectar como USUARIO_CHERRY y ejecutar desde la sección 1.
--   Sustituye USUARIO_CHERRY y '%' por el usuario/host reales
--   (SHOW GRANTS;  /  SELECT user, host FROM mysql.user;).
--
-- Opción C: si no se puede hacer GRANT, ver el final de este archivo.
-- =============================================================================

SET NAMES utf8mb4;

-- Sentinela de “nacimiento pendiente” (misma fecha que usa la API).
-- Si birth_date en origen es NULL, inválida, futura o de más de 100 años,
-- se guarda 2001-07-13 e is_minor = 0.

-- -----------------------------------------------------------------------------
-- 1) Diagnóstico (no escribe nada)
-- -----------------------------------------------------------------------------
SELECT
    COUNT(*) AS total_origen,
    SUM(document IS NULL OR TRIM(document) = '') AS sin_documento,
    SUM(email IS NULL OR TRIM(email) = '') AS sin_email,
    SUM(celphone IS NULL OR TRIM(celphone) = '') AS sin_celular,
    SUM(birth_date IS NULL) AS sin_nacimiento
FROM rcs_appointment.client;

-- Revisa estos valores: el CASE de mapeo solo acepta CC / TI / CE / PAS.
-- Si aparecen códigos distintos, ajústalo en el INSERT de la sección 3.
SELECT document_type, COUNT(*) AS n
FROM rcs_appointment.client
GROUP BY document_type
ORDER BY n DESC;

-- Duplicados de documento en origen (se conserva el id más alto)
SELECT TRIM(document) AS document_number, COUNT(*) AS n
FROM rcs_appointment.client
WHERE document IS NOT NULL AND TRIM(document) <> ''
GROUP BY TRIM(document)
HAVING COUNT(*) > 1
ORDER BY n DESC
LIMIT 50;

-- -----------------------------------------------------------------------------
-- 2) Tabla de mapeo de ids (auxiliar, en cherry_tatto)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cherry_tatto._import_rcs_client_map (
    rcs_client_id BIGINT NOT NULL,
    cherry_customer_id BIGINT UNSIGNED NOT NULL,
    imported_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (rcs_client_id),
    KEY idx_import_rcs_cherry_id (cherry_customer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- 3) Tabla auxiliar con filas ya mapeadas (sin WITH)
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS cherry_tatto._import_rcs_client_ready;

CREATE TABLE cherry_tatto._import_rcs_client_ready (
    rcs_client_id BIGINT NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    birth_date DATE NOT NULL,
    document_type ENUM('CC', 'TI', 'CE', 'PAS') NOT NULL,
    document_number VARCHAR(32) NOT NULL,
    email VARCHAR(255) NOT NULL,
    phone_number VARCHAR(32) NOT NULL,
    address VARCHAR(500) NULL,
    is_minor TINYINT(1) NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (rcs_client_id),
    KEY idx_import_ready_doc (document_number)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO cherry_tatto._import_rcs_client_ready (
    rcs_client_id,
    first_name,
    last_name,
    birth_date,
    document_type,
    document_number,
    email,
    phone_number,
    address,
    is_minor,
    created_at,
    updated_at
)
SELECT
    mapped.rcs_client_id,
    LEFT(TRIM(COALESCE(NULLIF(TRIM(mapped.first_name), ''), 'SIN NOMBRE')), 100) AS first_name,
    LEFT(TRIM(COALESCE(NULLIF(TRIM(mapped.last_name), ''), 'SIN APELLIDO')), 100) AS last_name,
    mapped.mapped_birth AS birth_date,
    CASE
        WHEN mapped.mapped_doc_type = 'TI'
             AND mapped.mapped_birth <> DATE('2001-07-13')
             AND TIMESTAMPDIFF(YEAR, mapped.mapped_birth, CURDATE()) >= 18
        THEN 'CC'
        ELSE mapped.mapped_doc_type
    END AS document_type,
    LEFT(TRIM(mapped.document), 32) AS document_number,
    LEFT(
        COALESCE(
            NULLIF(TRIM(mapped.email), ''),
            CONCAT('sin-correo-', LEFT(TRIM(mapped.document), 32), '@placeholder.local')
        ),
        255
    ) AS email,
    LEFT(COALESCE(NULLIF(TRIM(mapped.celphone), ''), '0000000'), 32) AS phone_number,
    NULLIF(LEFT(TRIM(mapped.address), 500), '') AS address,
    CASE
        WHEN mapped.mapped_birth = DATE('2001-07-13') THEN 0
        WHEN TIMESTAMPDIFF(YEAR, mapped.mapped_birth, CURDATE()) < 18 THEN 1
        ELSE 0
    END AS is_minor,
    COALESCE(mapped.created_date, CURRENT_TIMESTAMP) AS created_at,
    COALESCE(mapped.updated_date, mapped.created_date, CURRENT_TIMESTAMP) AS updated_at
FROM (
    SELECT
        c.id AS rcs_client_id,
        c.document,
        c.first_name,
        c.last_name,
        c.email,
        c.celphone,
        c.address,
        c.created_date,
        c.updated_date,
        CASE
            WHEN c.birth_date IS NULL THEN DATE('2001-07-13')
            WHEN CAST(c.birth_date AS CHAR) LIKE '0000-%' THEN DATE('2001-07-13')
            WHEN c.birth_date < DATE_SUB(CURDATE(), INTERVAL 100 YEAR) THEN DATE('2001-07-13')
            WHEN c.birth_date > CURDATE() THEN DATE('2001-07-13')
            ELSE c.birth_date
        END AS mapped_birth,
        CASE
            WHEN UPPER(REPLACE(REPLACE(TRIM(COALESCE(c.document_type, '')), '.', ''), ' ', '')) IN (
                'CC', 'CEDULA', 'CEDULADECIUDADANIA', 'CEDULADECIUDADANÍA', 'CÉDULA'
            ) THEN 'CC'
            WHEN UPPER(REPLACE(REPLACE(TRIM(COALESCE(c.document_type, '')), '.', ''), ' ', '')) IN (
                'TI', 'TARJETADEIDENTIDAD', 'TARJETAIDENTIDAD'
            ) THEN 'TI'
            WHEN UPPER(REPLACE(REPLACE(TRIM(COALESCE(c.document_type, '')), '.', ''), ' ', '')) IN (
                'CE', 'CEDULADEEXTRANJERIA', 'CEDULADEEXTRANJERÍA', 'CÉDULADEEXTRANJERÍA'
            ) THEN 'CE'
            WHEN UPPER(REPLACE(REPLACE(TRIM(COALESCE(c.document_type, '')), '.', ''), ' ', '')) IN (
                'PAS', 'PASAPORTE', 'PP', 'PASSPORT'
            ) THEN 'PAS'
            ELSE 'CC'
        END AS mapped_doc_type
    FROM rcs_appointment.client AS c
    WHERE c.document IS NOT NULL AND TRIM(c.document) <> ''
) AS mapped
INNER JOIN (
    SELECT TRIM(document) AS document_number, MAX(id) AS keep_id
    FROM rcs_appointment.client
    WHERE document IS NOT NULL AND TRIM(document) <> ''
    GROUP BY TRIM(document)
) AS keep ON keep.keep_id = mapped.rcs_client_id;

-- Vista previa (primeras 100 filas que se insertarían)
SELECT
    r.rcs_client_id,
    r.first_name,
    r.last_name,
    r.document_type,
    r.document_number,
    r.email,
    r.phone_number,
    r.birth_date,
    r.is_minor,
    r.address,
    r.created_at
FROM cherry_tatto._import_rcs_client_ready AS r
LEFT JOIN cherry_tatto.customers AS dest
    ON dest.document_number = r.document_number
WHERE dest.id IS NULL
ORDER BY r.rcs_client_id
LIMIT 100;

SELECT COUNT(*) AS filas_a_insertar
FROM cherry_tatto._import_rcs_client_ready AS r
LEFT JOIN cherry_tatto.customers AS dest
    ON dest.document_number = r.document_number
WHERE dest.id IS NULL;

-- -----------------------------------------------------------------------------
-- 4) Inserción
--    Ejecuta el bloque, revisa los conteos y luego descomenta COMMIT
--    (o ejecuta ROLLBACK si algo no cuadra).
-- -----------------------------------------------------------------------------
START TRANSACTION;

INSERT INTO cherry_tatto.customers (
    first_name,
    last_name,
    birth_date,
    document_type,
    document_number,
    document_issue_date,
    email,
    phone_number,
    address,
    nationality,
    profession,
    social_media,
    emergency_contact_name,
    emergency_contact_phone,
    is_minor,
    guardian_name,
    guardian_document_type,
    guardian_document_number,
    guardian_document_issue_date,
    deleted_at,
    created_at,
    updated_at
)
SELECT
    r.first_name,
    r.last_name,
    r.birth_date,
    r.document_type,
    r.document_number,
    NULL,
    r.email,
    r.phone_number,
    r.address,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    r.is_minor,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    r.created_at,
    r.updated_at
FROM cherry_tatto._import_rcs_client_ready AS r
LEFT JOIN cherry_tatto.customers AS dest
    ON dest.document_number = r.document_number
WHERE dest.id IS NULL;

SET @clientes_insertados := ROW_COUNT();

INSERT IGNORE INTO cherry_tatto._import_rcs_client_map (rcs_client_id, cherry_customer_id)
SELECT c.id, dest.id
FROM rcs_appointment.client AS c
INNER JOIN cherry_tatto.customers AS dest
    ON dest.document_number = LEFT(TRIM(c.document), 32)
WHERE c.document IS NOT NULL AND TRIM(c.document) <> '';

SELECT
    @clientes_insertados AS clientes_insertados,
    (SELECT COUNT(*) FROM rcs_appointment.client) AS filas_origen,
    (SELECT COUNT(*) FROM cherry_tatto.customers) AS clientes_destino,
    (SELECT COUNT(*) FROM cherry_tatto._import_rcs_client_map) AS ids_mapeados;

-- Descomenta UNA de las dos líneas:
-- COMMIT;
-- ROLLBACK;

-- -----------------------------------------------------------------------------
-- 5) Comprobaciones (después del COMMIT)
-- -----------------------------------------------------------------------------
-- Filas de RCS que no quedaron mapeadas (sin documento, o no coincidió)
SELECT c.id, c.first_name, c.last_name, c.document, c.email, c.celphone
FROM rcs_appointment.client AS c
LEFT JOIN cherry_tatto._import_rcs_client_map AS m ON m.rcs_client_id = c.id
WHERE m.rcs_client_id IS NULL
LIMIT 100;

-- Opcional: borrar la tabla auxiliar de mapeo de columnas (no el mapa de ids)
-- DROP TABLE IF EXISTS cherry_tatto._import_rcs_client_ready;

-- =============================================================================
-- Opción C: dos usuarios sin GRANT cruzado
-- =============================================================================
-- Conectar como usuario de rcs_appointment y generar sentencias:
--
-- SELECT CONCAT(
--     'INSERT IGNORE INTO customers (first_name, last_name, birth_date, document_type, ',
--     'document_number, email, phone_number, address, is_minor, created_at, updated_at) VALUES (',
--     QUOTE(LEFT(TRIM(COALESCE(NULLIF(TRIM(first_name), ''), 'SIN NOMBRE')), 100)), ', ',
--     QUOTE(LEFT(TRIM(COALESCE(NULLIF(TRIM(last_name), ''), 'SIN APELLIDO')), 100)), ', ',
--     QUOTE(COALESCE(NULLIF(birth_date, '0000-00-00'), '2001-07-13')), ', ',
--     QUOTE('CC'), ', ',
--     QUOTE(LEFT(TRIM(document), 32)), ', ',
--     QUOTE(LEFT(COALESCE(NULLIF(TRIM(email), ''), CONCAT('sin-correo-', LEFT(TRIM(document), 32), '@placeholder.local')), 255)), ', ',
--     QUOTE(LEFT(COALESCE(NULLIF(TRIM(celphone), ''), '0000000'), 32)), ', ',
--     IF(address IS NULL OR TRIM(address) = '', 'NULL', QUOTE(LEFT(TRIM(address), 500))), ', ',
--     '0, ',
--     QUOTE(COALESCE(created_date, NOW())), ', ',
--     QUOTE(COALESCE(updated_date, created_date, NOW())),
--     ');'
-- ) AS stmt
-- FROM rcs_appointment.client
-- WHERE document IS NOT NULL AND TRIM(document) <> '';
--
-- Guardar el resultado y ejecutarlo conectado a cherry_tatto.
-- =============================================================================
