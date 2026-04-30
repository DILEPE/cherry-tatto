-- Permitir insertar menores sin tutor completo (completar después del agendamiento o en administración).
-- Si tu esquema no tiene este CHECK (p. ej. solo corriste 000), este ALTER puede fallar: ignóralo o ajusta el nombre.

USE cherry_tatto;

ALTER TABLE customers DROP CHECK chk_customers_minor_guardian;
