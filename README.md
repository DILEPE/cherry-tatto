# Cherry Tattoo — Panel de gestión

Aplicación para administrar citas, clientes, contratos digitales y encuestas, integrada con una **API REST (Litestar)** y un **panel web (Angular)** que consumen una base **MySQL**.

## Estructura general del programa

```
cherry_tattoo/
├── app/                 # API Litestar (backend) + assets (logos Rock City, plantillas HTML, n8n)
├── scripts/             # Arranque API, semillas, utilidades
├── sql/                 # Esquema inicial y migraciones incrementales
├── docs/                # Documentación adicional del repositorio
├── Launch-Cherry-Dev-Stack.bat          # Windows: API + panel Angular (+ n8n); doble clic
├── Install-Cherry-Desktop-Shortcut.bat  # Acceso directo escritorio
├── requirements.txt     # Dependencias Python (solo backend)
└── .env                 # Variables de entorno (no versionar)
```

### Componentes

| Componente | Rol |
|------------|-----|
| **API (`app/`)** | Expone recursos HTTP: citas, clientes, contratos, plantillas, salud, encuestas. Persistencia en MySQL. |
| **Panel Angular** | UI operativa en el repositorio **`cherry_tattoo_angular`** (hermano de este repo). |
| **MySQL** | Base de datos relacional: clientes, citas, contratos, plantillas, pagos, etc. |
| **n8n (opcional)** | Webhooks para notificaciones tras eventos (p. ej. contrato firmado); la URL se configura en `.env`. |

Para el **mapa de carpetas y capas del código Python**, consulta [docs/ESTRUCTURA_CODIGO.md](docs/ESTRUCTURA_CODIGO.md).

---

## Instalación desde cero

### Requisitos previos

- **Python 3.11+** (recomendado; compatible con 3.10+ si las dependencias lo permitienen).
- **Node.js 20+** y npm (panel Angular).
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

# Opcional: notificaciones n8n
# N8N_WEBHOOK_URL=https://tu-n8n/webhook/...

# Tipos de servicio en citas (debe coincidir con VARCHAR/ENUM en MySQL)
SERVICE_TYPE_ENUM_VALUES=Tatuaje,Piercing,Cambio,Limpieza

# Login del panel (API). Tras sql/015_panel_users.sql:
# PANEL_AUTH_USERS_SOURCE=database
```

Ajusta `DB_*` y `SERVICE_TYPE_ENUM_VALUES` según tu despliegue.

Con **`PANEL_AUTH_USERS_SOURCE=database`**, el login del panel Angular usa `POST /api/panel-users/login` contra la tabla `panel_users` (aplica **`015_panel_users.sql`** y migraciones de módulos de usuario).

Para crear o actualizar un usuario administrador del panel con bcrypt:

```bash
py -m pip install -r requirements.txt
python scripts/create_panel_user.py --username admin --password cherrytattoo2026
python scripts/create_panel_user.py --username admin --password cherrytattoo2026 --apply
# Windows, si ejecutas fuera de la raiz del repo o tu .env esta en otra carpeta:
py scripts/create_panel_user.py --env-file C:\ruta\a\.env --username admin --password cherrytattoo2026 --apply
```

El comando sin `--apply` solo simula la accion; `--apply` escribe en MySQL usando las variables `DB_*` del `.env`.

### 4. Arrancar la API (Litestar + Uvicorn)

Desde la **raíz del repositorio**, con el virtualenv activado:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 5000
```

El puerto puede coincidir con `PORT` en `.env`; Uvicorn usa el que indiques en la línea de comandos.

Comprueba salud: `GET http://127.0.0.1:5000/health` (o la ruta que exponga tu `HealthController`).

### 5. Arrancar el panel Angular

En **otra terminal**, en el repositorio `cherry_tattoo_angular` (junto a este repo):

```powershell
cd ..\cherry_tattoo_angular
npm install
npm start
```

Abre `http://localhost:4200`. El proxy reenvía `/api` al backend en el puerto 5000.

### Arranque conjunto con scripts (API + panel opcional + n8n)

En la **raíz del repositorio** puedes levantar la API y (opcionalmente) **n8n** y el panel Angular.

| Archivo | Entorno | Descripción |
|---------|---------|-------------|
| [`scripts/dev-stack.ps1`](scripts/dev-stack.ps1) | Windows (PowerShell) | Resuelve `docker.exe` y `npx` aunque no estén en el PATH (rutas habituales de instalación). |
| [`scripts/dev-stack.sh`](scripts/dev-stack.sh) | Linux, macOS, Git Bash | Arranque conjunto en entorno tipo Unix. |
| [`Launch-Cherry-Dev-Stack.bat`](Launch-Cherry-Dev-Stack.bat) | Windows | Antepone al PATH rutas típicas de Docker Desktop y Node.js y ejecuta `scripts\dev-stack.ps1`. |
| [`Install-Cherry-Desktop-Shortcut.bat`](Install-Cherry-Desktop-Shortcut.bat) | Windows | Ejecutar **una vez** desde el repo: crea en el escritorio el acceso directo **Cherry Tattoo Dev** y `Cherry-Tattoo-Iniciar.bat`, que invocan el lanzador por ruta absoluta. |
| [`scripts/install-desktop-shortcut.ps1`](scripts/install-desktop-shortcut.ps1) | Windows | Lo usa el instalador anterior; también puedes llamarlo con `-RepoRoot "ruta\al\repo"`. |

**Doble clic en Windows:** `Launch-Cherry-Dev-Stack.bat` arranca API y, si existe `../cherry_tattoo_angular`, el panel (`npm start` en ventana aparte). Solo API: `set START_PANEL=0` antes del BAT o del script. Ruta custom del panel: `CHERRY_ANGULAR_ROOT`.

**Entorno virtual:** los scripts buscan Python en `.venv\Scripts\python.exe` o `venv\Scripts\python.exe` (en ese orden). Opcional: variable `CHERRY_PYTHON` con la ruta absoluta a `python.exe`.

**n8n:** por defecto el modo es **`auto`**: intenta **Node.js (`npx n8n`)** primero (sin Docker); si no hay `npx`, intenta **Docker**. Variables útiles:

- `START_N8N` — `auto` (por defecto si no la defines), `npx`, `docker`, `none` / `0` para no levantar n8n.
- `N8N_PORT` — puerto local (por defecto `5678`).

Ejemplos en PowerShell:

```powershell
.\scripts\dev-stack.ps1
$env:START_N8N = "none"; .\scripts\dev-stack.ps1   # sin n8n
.\scripts\dev-stack.ps1 -N8nMode docker
```

En Git Bash / Linux:

```bash
bash scripts/dev-stack.sh
START_N8N=0 bash scripts/dev-stack.sh
```

Otros puertos: `API_PORT`, `PANEL_PORT` (por defecto 4200) y `N8N_PORT`.

**Importante:** no copies `Launch-Cherry-Dev-Stack.bat` suelto al escritorio (no encontrará `scripts\dev-stack.ps1`). Usa `Install-Cherry-Desktop-Shortcut.bat` o define la variable de usuario **`CHERRY_TATTOO_ROOT`** con la ruta del repositorio si mantienes un lanzador personalizado.

### Acceso desde la red local y firewall (Windows)

Por defecto la API escucha en **`127.0.0.1`**. Para acceso en LAN:

1. Arranca la API con **`DEV_BIND_HOST=0.0.0.0`** y el panel Angular con `ng serve --host 0.0.0.0` (o el proxy configurado en tu entorno).
2. URLs: `http://<IPv4-de-esta-PC>:4200` (panel) y `:5000` (API). Ayuda: `.\scripts\show-lan-url.ps1`
3. **Firewall:** permite TCP en **5000**, **4200** y **5678** (n8n) si aplica.

### 6. Verificación rápida

1. API responde sin errores de conexión a MySQL (`GET /health`).
2. Panel Angular inicia sesión y carga citas sin errores HTTP.
3. Assets de marca en `app/assets/` (`rock_city_watermark.png`, `receipt_rock_city_logo.png`).

---

## Desarrollo

- **Ramas:** convención `feature/...` desde `develop`; commits y PRs en español según las reglas del equipo.
- **Migraciones:** nuevos cambios de esquema en `sql/NNN_descripcion.sql` y documentar orden en `sql/README.md` si aplica.
- **Documentación con PRs grandes:** si introduces cambios **importantes** en **infraestructura** (BD, migraciones, variables de entorno, despliegue, integraciones externas) o en **componentes** (rutas o contratos de API, capas de dominio/repositorio nuevas), actualiza en el mismo PR el **README** de la raíz, [docs/ESTRUCTURA_CODIGO.md](docs/ESTRUCTURA_CODIGO.md) y, si afecta al esquema, [sql/README.md](sql/README.md).
- **Panel UI:** el desarrollo del frontend vive en el repositorio **`cherry_tattoo_angular`**.

---

## Enlaces útiles

- [Estructura interna del código](docs/ESTRUCTURA_CODIGO.md)
- [Scripts SQL y orden de ejecución](sql/README.md)
