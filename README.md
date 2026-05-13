# Cherry Tattoo — Panel de gestión

Aplicación para administrar citas, clientes, contratos digitales y encuestas, integrada con una **API REST (Litestar)** y un **panel web (Streamlit)** que consumen una base **MySQL**.

## Estructura general del programa

```
cherry_tattoo/
├── app/                 # API Litestar (backend)
├── streamlit_app/       # Interfaz Streamlit (frontend operativo)
├── sql/                 # Esquema inicial y migraciones incrementales
├── docs/                # Documentación adicional del repositorio
├── requirements.txt     # Dependencias Python
└── .env                 # Variables de entorno (no versionar; crear en cada entorno)
```

### Componentes

| Componente | Rol |
|------------|-----|
| **API (`app/`)** | Expone recursos HTTP: citas, clientes, contratos, plantillas, salud, encuestas. Persistencia en MySQL. |
| **Streamlit (`streamlit_app/`)** | Panel para agenda, clientes, firma de contratos, administración de plantillas y reportes. Habla con la API vía HTTP. |
| **MySQL** | Base de datos relacional: clientes, citas, contratos, plantillas, pagos, etc. |
| **n8n (opcional)** | Webhooks para notificaciones tras eventos (p. ej. contrato firmado); la URL se configura en `.env`. |

Para el **mapa de carpetas y capas del código Python**, consulta [docs/ESTRUCTURA_CODIGO.md](docs/ESTRUCTURA_CODIGO.md).

---

## Instalación desde cero

### Requisitos previos

- **Python 3.11+** (recomendado; compatible con 3.10+ si las dependencias lo permiten).
- **MySQL 8** (o compatible) con usuario con permisos para crear/esquema y tablas.
- **Git** (para clonar el repositorio).

### 1. Clonar y entorno virtual

```powershell
git clone https://github.com/DILEPE/cherry-tatto.git
cd cherry-tatto

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

En Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Base de datos MySQL

1. Crea una base de datos, por ejemplo `cherry_tatto` o el nombre que usarás en `.env`.
2. Ejecuta los scripts SQL **en el orden indicado** en [sql/README.md](sql/README.md).

Resumen para **entorno nuevo** (ajusta si tu rama ya incluye scripts posteriores):

1. `sql/000_initial_schema_cherry_tatto.sql`
2. `002` … `007` según `sql/README.md`
3. Migraciones adicionales del repositorio en orden numérico (`008_…`, `009_…`, `010_…`, etc.)

> El script `010_contract_templates_contract_kind.sql` es **idempotente**; si tu tabla `contract_templates` ya existía con otro índice único, revísalo antes en Workbench.

### 3. Archivo `.env` en la raíz del proyecto

Crea un archivo `.env` junto a `requirements.txt` (no lo subas a Git). Ejemplo **mínimo** para arrancar:

```env
# MySQL (API)
DB_HOST=127.0.0.1
DB_USER=tu_usuario
DB_PASSWORD=tu_password
DB_NAME=cherry_tatto

# API
PORT=5000
LOG_LEVEL=INFO
DEBUG=True

# Streamlit → API (misma máquina por defecto)
API_BASE_URL=http://127.0.0.1:5000

# Opcional: notificaciones n8n
# N8N_WEBHOOK_URL=https://tu-n8n/webhook/...

# Tipos de servicio en citas (debe coincidir con VARCHAR/ENUM en MySQL)
SERVICE_TYPE_ENUM_VALUES=Tatuaje,Piercing,Cambio,Limpieza

# Login del panel Streamlit (opcional). Valores reconocidos para activar: 1, true, yes, on
# (sin distinguir mayúsculas). Las rutas ?view=contract_sign y ?view=contract_read son navegación interna
# del mismo Streamlit; con PANEL_AUTH_ENABLED activo exigen la misma sesión del panel que el resto de la app.
# PANEL_AUTH_ENABLED=1
# PANEL_LOGIN_USER=operador
# PANEL_LOGIN_PASSWORD=elige-una-contraseña-segura
# PANEL_AUTH_USERS_SOURCE=database
# Tras ejecutar sql/015_panel_users.sql: registro e inicio de sesión contra tabla panel_users (API en marcha).
```

Ajusta `DB_*`, `API_BASE_URL` (si la API corre en otro host/puerto) y `SERVICE_TYPE_ENUM_VALUES` según tu despliegue. En desarrollo suele convenir dejar `PANEL_AUTH_ENABLED` sin definir o en falso para no pedir usuario al abrir el panel.

Con **`PANEL_AUTH_USERS_SOURCE=database`**, los usuarios se crean desde el panel (pestaña **Crear cuenta**) o vía `POST /api/panel-users/register`; hace falta haber aplicado **`015_panel_users.sql`** y tener la API accesible en `API_BASE_URL`. Con **`PANEL_AUTH_USERS_SOURCE=env`** (por defecto si no defines la variable), el login sigue usando solo `PANEL_LOGIN_USER` y `PANEL_LOGIN_PASSWORD`.

### 4. Arrancar la API (Litestar + Uvicorn)

Desde la **raíz del repositorio**, con el virtualenv activado:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 5000
```

El puerto puede coincidir con `PORT` en `.env`; Uvicorn usa el que indiques en la línea de comandos.

Comprueba salud: `GET http://127.0.0.1:5000/health` (o la ruta que exponga tu `HealthController`).

### 5. Arrancar el panel Streamlit

En **otra terminal**, misma raíz y mismo `venv`:

```powershell
python -m streamlit run streamlit_app/main.py
```

Streamlit leerá `.env` (vía `streamlit_app/main.py`) y llamará a la API en `API_BASE_URL`.

### 6. Verificación rápida

1. API responde sin errores de conexión a MySQL.
2. Streamlit abre el navegador; las pestañas que listan datos no muestran errores HTTP al cargar.
3. Opcional: logo `branding.png` en `streamlit_app/assets/` o `assets/`.

---

## Desarrollo

- **Ramas:** convención `feature/...` desde `develop`; commits y PRs en español según las reglas del equipo.
- **Migraciones:** nuevos cambios de esquema en `sql/NNN_descripcion.sql` y documentar orden en `sql/README.md` si aplica.
- **Documentación con PRs grandes:** si introduces cambios **importantes** en **infraestructura** (BD, migraciones, variables de entorno, despliegue, integraciones externas) o en **componentes** (nuevos flujos en Streamlit, rutas o contratos de API, capas de dominio/repositorio nuevas o muy distintas), actualiza en el mismo PR el **README** de la raíz, [docs/ESTRUCTURA_CODIGO.md](docs/ESTRUCTURA_CODIGO.md) y, si afecta al esquema, [sql/README.md](sql/README.md).

---

## Enlaces útiles

- [Estructura interna del código](docs/ESTRUCTURA_CODIGO.md)
- [Scripts SQL y orden de ejecución](sql/README.md)
