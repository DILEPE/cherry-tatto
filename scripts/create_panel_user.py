#!/usr/bin/env python3
"""
Crea o actualiza un usuario de `panel_users` usando bcrypt.

Uso desde la raiz del proyecto::

    python scripts/create_panel_user.py --username admin --password cherrytattoo2026
    python scripts/create_panel_user.py --username admin --password cherrytattoo2026 --apply
    python scripts/create_panel_user.py --env-file C:\\ruta\\a\\.env --username admin --password cherrytattoo2026 --apply

Sin `--apply`, solo muestra que haria. Con `--apply`, inserta el usuario o
actualiza su contrasena si el username ya existe.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ENV_EXAMPLE_KEYS = ("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME")

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[misc, assignment]

_USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,80}$")
_ROLE_CHOICES = ("administrador", "vendedor", "perforador", "tatuador")


def _strip_env_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _load_env_file_without_dotenv(path: Path) -> bool:
    if not path.is_file():
        return False

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = _strip_env_quotes(value.strip())
        os.environ.setdefault(key, value)
    return True


def _load_env_files(env_file: str | None) -> list[Path]:
    candidates: list[Path] = []
    if env_file:
        candidates.append(Path(env_file).expanduser())
    else:
        candidates.extend([Path.cwd() / ".env", _REPO_ROOT / ".env"])

    loaded: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        path = candidate.resolve()
        if path in seen:
            continue
        seen.add(path)
        if not path.is_file():
            continue
        if load_dotenv:
            load_dotenv(path, override=False)
            loaded.append(path)
        elif _load_env_file_without_dotenv(path):
            loaded.append(path)
    return loaded


def _load_bcrypt() -> Any:
    try:
        import bcrypt
    except ImportError as exc:
        raise RuntimeError("Instala dependencias: pip install bcrypt") from exc
    return bcrypt


def _load_mysql_connector() -> tuple[Any, type[Exception]]:
    try:
        import mysql.connector
        from mysql.connector import Error as MySQLError
    except ImportError as exc:
        raise RuntimeError("Instala dependencias: pip install mysql-connector-python python-dotenv") from exc
    return mysql.connector, MySQLError


def _hash_password(plain: str, bcrypt_module: Any) -> str:
    return bcrypt_module.hashpw(plain.encode("utf-8"), bcrypt_module.gensalt()).decode("ascii")


def _normalize_username(raw: str) -> str:
    username = raw.strip().lower()
    if not _USERNAME_RE.fullmatch(username):
        raise ValueError(
            "El usuario debe tener entre 3 y 80 caracteres: letras minusculas, "
            "numeros, punto, guion o guion bajo."
        )
    return username


def _optional_text(raw: str | None, max_len: int) -> str | None:
    if raw is None:
        return None
    value = raw.strip()
    return value[:max_len] if value else None


def _required_env(name: str, default: str | None = None, *, allow_empty: bool = False) -> str:
    value = os.getenv(name, default)
    if value is None or (value == "" and not allow_empty):
        raise ValueError(f"Define {name} en .env o como variable de entorno.")
    return value


def _table_exists(cursor: Any, table_name: str) -> bool:
    cursor.execute(
        """
        SELECT COUNT(*) AS c
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name = %s
        """,
        (table_name,),
    )
    row = cursor.fetchone()
    return bool(row and int(row["c"]) > 0)


def _columns_for_table(cursor: Any, table_name: str) -> set[str]:
    cursor.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = %s
        """,
        (table_name,),
    )
    return {str(row["column_name"]) for row in cursor.fetchall()}


def _resolve_store_id(cursor: Any, store_id: int | None, store_name: str) -> int:
    if store_id is not None:
        cursor.execute(
            """
            SELECT id
            FROM stores
            WHERE id = %s
              AND deleted_at IS NULL
              AND is_active = 1
            LIMIT 1
            """,
            (store_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"No existe una tienda activa con id={store_id}.")
        return int(row["id"])

    cursor.execute(
        """
        SELECT id
        FROM stores
        WHERE name = %s
          AND deleted_at IS NULL
          AND is_active = 1
        ORDER BY id ASC
        LIMIT 1
        """,
        (store_name,),
    )
    row = cursor.fetchone()
    if row:
        return int(row["id"])

    cursor.execute(
        """
        SELECT id, name
        FROM stores
        WHERE deleted_at IS NULL
          AND is_active = 1
        ORDER BY id ASC
        LIMIT 1
        """
    )
    row = cursor.fetchone()
    if not row:
        raise ValueError("No hay tiendas activas en `stores`; ejecuta primero la migracion 024.")
    print(
        f"No se encontro la tienda '{store_name}'. Se usara la primera activa: "
        f"{row['name']} (id={row['id']})."
    )
    return int(row["id"])


def _existing_user_id(cursor: Any, username: str) -> int | None:
    cursor.execute(
        """
        SELECT id
        FROM panel_users
        WHERE username = %s
        LIMIT 1
        """,
        (username,),
    )
    row = cursor.fetchone()
    return int(row["id"]) if row else None


def _insert_user(cursor: Any, fields: dict[str, Any]) -> int:
    columns = list(fields.keys())
    placeholders = ", ".join(["%s"] * len(columns))
    cursor.execute(
        f"""
        INSERT INTO panel_users ({", ".join(columns)})
        VALUES ({placeholders})
        """,
        tuple(fields[column] for column in columns),
    )
    return int(cursor.lastrowid or 0)


def _update_user(cursor: Any, user_id: int, fields: dict[str, Any]) -> None:
    sets = ", ".join(f"{column} = %s" for column in fields)
    values = list(fields.values())
    values.append(user_id)
    cursor.execute(
        f"""
        UPDATE panel_users
        SET {sets}
        WHERE id = %s
        """,
        tuple(values),
    )


def _build_payload(cursor: Any, args: argparse.Namespace, columns: set[str], password_hash: str) -> dict[str, Any]:
    required = {"username", "password_hash", "is_active"}
    missing = required - columns
    if missing:
        raise ValueError(f"Faltan columnas requeridas en panel_users: {', '.join(sorted(missing))}")

    fields: dict[str, Any] = {
        "username": args.username,
        "password_hash": password_hash,
        "is_active": 1 if args.active else 0,
    }

    optional_values: dict[str, Any] = {
        "first_name": args.first_name,
        "last_name": args.last_name,
        "address": args.address,
        "phone": args.phone,
        "role": args.role,
    }
    for column, value in optional_values.items():
        if column in columns:
            fields[column] = value

    if "store_id" in columns:
        if not _table_exists(cursor, "stores"):
            raise ValueError("La tabla `stores` no existe; ejecuta primero la migracion 024.")
        fields["store_id"] = _resolve_store_id(cursor, args.store_id, args.store_name)

    return fields


def main() -> int:
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--env-file")
    pre_args, _ = pre_parser.parse_known_args()
    loaded_env_files = _load_env_files(pre_args.env_file)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        help="Ruta al archivo .env. Si se omite, busca .env en el directorio actual y en la raiz del repo.",
    )
    parser.add_argument("--username", default=os.getenv("PANEL_USER_USERNAME", "admin"))
    parser.add_argument("--password", default=os.getenv("PANEL_USER_PASSWORD"))
    parser.add_argument("--first-name", default=os.getenv("PANEL_USER_FIRST_NAME", "Admin"))
    parser.add_argument("--last-name", default=os.getenv("PANEL_USER_LAST_NAME", "Cherry Tattoo"))
    parser.add_argument("--address", default=os.getenv("PANEL_USER_ADDRESS"))
    parser.add_argument("--phone", default=os.getenv("PANEL_USER_PHONE"))
    parser.add_argument("--store-id", type=int, default=None)
    parser.add_argument("--store-name", default=os.getenv("PANEL_USER_STORE_NAME", "Cherry Tattoo"))
    parser.add_argument("--role", choices=_ROLE_CHOICES, default=os.getenv("PANEL_USER_ROLE", "administrador"))
    parser.add_argument("--inactive", action="store_true", help="Crea o actualiza el usuario como inactivo.")
    parser.add_argument(
        "--no-update-existing",
        action="store_true",
        help="Falla si el username ya existe, en vez de actualizarlo.",
    )
    parser.add_argument("--apply", action="store_true", help="Escribe los cambios en MySQL.")
    parser.add_argument("--dry-run", action="store_true", help="Fuerza solo simulacion aunque exista --apply.")
    args = parser.parse_args()

    try:
        args.username = _normalize_username(args.username)
        if not args.password:
            raise ValueError("Indica --password o define PANEL_USER_PASSWORD.")
        if not (8 <= len(args.password.encode("utf-8")) <= 72):
            raise ValueError("La contrasena debe tener entre 8 y 72 bytes para bcrypt.")
        if args.role not in _ROLE_CHOICES:
            raise ValueError(f"Rol invalido: {args.role}. Usa: {', '.join(_ROLE_CHOICES)}.")
        args.first_name = (_optional_text(args.first_name, 100) or "")
        args.last_name = (_optional_text(args.last_name, 100) or "")
        args.address = _optional_text(args.address, 500)
        args.phone = _optional_text(args.phone, 32)
        args.active = not bool(args.inactive)

        host = _required_env("DB_HOST")
        user = _required_env("DB_USER")
        db_password = _required_env("DB_PASSWORD", "", allow_empty=True)
        database = os.getenv("DB_NAME", "cherry_tatto")
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        if loaded_env_files:
            loaded = ", ".join(str(path) for path in loaded_env_files)
            print(f"Archivos .env cargados: {loaded}", file=sys.stderr)
            print("Verifica que el archivo cargado tenga DB_HOST=... sin espacios antes del '='.", file=sys.stderr)
        else:
            print(
                "No se cargo ningun .env. Ejecuta desde la raiz del repo o usa "
                "--env-file C:\\ruta\\a\\.env.",
                file=sys.stderr,
            )
        return 1

    write_db = bool(args.apply) and not bool(args.dry_run)
    if loaded_env_files:
        loaded = ", ".join(str(path) for path in loaded_env_files)
        print(f"Archivo .env cargado: {loaded}")
    else:
        found_any_db_env = any(os.getenv(key) is not None for key in _ENV_EXAMPLE_KEYS)
        if not found_any_db_env:
            print(
                "No se encontro un archivo .env ni variables DB_* en el entorno actual. "
                "Puedes indicar la ruta con --env-file.",
                file=sys.stderr,
            )
    print(f"Base de datos: {database} en {host}")
    print(f"Usuario panel: {args.username}")
    print(f"Rol: {args.role} | Estado: {'activo' if args.active else 'inactivo'}")
    print(f"Modo: {'APLICAR' if write_db else 'SIMULACION'}")

    try:
        mysql_connector, mysql_error = _load_mysql_connector()
        bcrypt_module = _load_bcrypt() if write_db else None
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    try:
        conn = mysql_connector.connect(host=host, user=user, password=db_password, database=database)
    except mysql_error as exc:
        print(f"No se pudo conectar a MySQL ({database}): {exc}", file=sys.stderr)
        return 1

    cursor = conn.cursor(dictionary=True, buffered=True)
    try:
        if not _table_exists(cursor, "panel_users"):
            print("La tabla `panel_users` no existe; ejecuta primero sql/015_panel_users.sql.", file=sys.stderr)
            return 1

        columns = _columns_for_table(cursor, "panel_users")
        existing_id = _existing_user_id(cursor, args.username)
        if existing_id and args.no_update_existing:
            print(f"El usuario '{args.username}' ya existe con id={existing_id}.", file=sys.stderr)
            return 1

        password_hash = (
            _hash_password(args.password, bcrypt_module)
            if write_db
            else "$2b$<generado-solo-con-apply>"
        )
        fields = _build_payload(cursor, args, columns, password_hash)

        if existing_id:
            update_fields = {k: v for k, v in fields.items() if k != "username"}
            print(f"Accion: actualizar usuario existente id={existing_id}.")
            if write_db:
                _update_user(cursor, existing_id, update_fields)
                conn.commit()
                print("Usuario actualizado correctamente.")
        else:
            print("Accion: crear usuario nuevo.")
            if write_db:
                new_id = _insert_user(cursor, fields)
                conn.commit()
                print(f"Usuario creado correctamente con id={new_id}.")

        if not write_db:
            print("Usa --apply para escribir los cambios.")
        return 0
    except mysql_error as exc:
        conn.rollback()
        print(f"Error MySQL: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        conn.rollback()
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
