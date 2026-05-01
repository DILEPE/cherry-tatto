# Estructura interna del código

Este documento describe cómo está organizado el repositorio **cherry_tattoo** a nivel de módulos y responsabilidades. Complementa el [README principal](../README.md) (instalación y visión general).

## Principio general

El backend sigue una separación en capas inspirada en **hexagonal / limpia**:

1. **Dominio** — reglas de negocio y modelos lógicos (sin detalles de HTTP ni SQL).
2. **Aplicación** — controladores HTTP (Litestar): entrada/salida, códigos, validación Pydantic.
3. **Infraestructura** — MySQL, repositorios, integraciones externas (p. ej. n8n).
4. **Esquemas (Pydantic)** — contratos de API: request/response compartidos con validación.

El **Streamlit** es un cliente más: no contiene reglas de persistencia directa; usa `streamlit_app/api_client.py` para hablar con la API.

```
app/
├── main.py                 # Punto de entrada Litestar, wiring DI manual, CORS
├── application/            # Controllers (rutas HTTP)
├── domain/                 # Servicios de negocio, modelos dataclass, utilidades de dominio
├── infrastructure/         # DB, repositorios SQL, notificaciones
├── schemas/              # Pydantic: DTOs de API
└── types/                # Tipos auxiliares (p. ej. JSON)

streamlit_app/
├── main.py                 # App Streamlit multipágina / query params
├── api_client.py           # Cliente HTTP centralizado (requests)
├── citas_tab.py            # Calendario, citas, reportes
├── customers_management.py # CRUD clientes en UI
├── contract_signing.py     # Flujo firma por cita (URL dedicada)
├── contract_read_view.py   # Lectura contrato firmado
├── contracts_admin.py      # Gestión plantillas de contrato
├── survey_questions_admin.py # CRUD preguntas de encuesta (vincula con reporte)
├── validation.py           # Validaciones compartidas en formularios
├── customer_sync.py        # Helpers cliente ↔ API
└── rich_text.py            # Editor enriquecido opcional (Quill) para plantillas
```

---

## Backend (`app/`)

### `app/main.py`

- Carga `.env` con `python-dotenv`.
- Instancia `DatabaseManager`, repositorios (`AppointmentRepository`, `CustomerRepository`), `NotificationService` y `BusinessLogicService`.
- Registra controladores en `Litestar` y expone `app` para Uvicorn.

### `app/application/*_controller.py`

Cada controlador agrupa rutas bajo un prefijo (p. ej. `/api/appointments`). Responsabilidades típicas:

- Recibir cuerpos/query ya validados por Pydantic (donde aplica).
- Invocar métodos asíncronos de `BusinessLogicService` vía `state.service`.
- Traducir excepciones a `HTTPException`.

Archivos habituales: `appointment_controller`, `customer_controller`, `contract_controller`, `template_controller`, `survey_controller`, `survey_questions_controller`, `health_controller`.

### `app/domain/`

| Módulo | Contenido |
|--------|-----------|
| `services.py` | `BusinessLogicService`: orquestación de casos de uso (citas, contratos, plantillas, clientes, reportes). Ejecuta trabajo bloqueante en `asyncio.to_thread` cuando llama al repositorio. |
| `models.py` | Dataclasses de entrada/salida del dominio (`AppointmentCreate`, `ContractSign`, `ContractTemplate`, etc.). |
| `service_types.py` | Resolución de texto de servicio → valor almacenado en cita (`SERVICE_TYPE_ENUM_VALUES`). |
| `contract_kinds.py` | Mapeo cita → tipo de plantilla (`tattoo` / `piercing`) y si la cita **requiere** contrato (p. ej. Cambio/Limpieza no). |

### `app/infrastructure/`

| Módulo | Contenido |
|--------|-----------|
| `database.py` | `DatabaseManager`: conexión MySQL, utilidades de migración ligera en arranque (`ensure_*`). |
| `repositories.py` | `AppointmentRepository`: citas, contratos, plantillas de contrato, reportes relacionados. |
| `customer_repository.py` | Persistencia específica de clientes (puede evolucionar aparte del repo de citas). |
| `external_api.py` | Envío de notificaciones (webhook). |
| Otros | Health n8n, etc., según evolución del repo. |

### `app/schemas/`

Modelos Pydantic v2 por contexto: `appointment`, `customer`, `contract`, `template`, `survey`, `survey_questions`, `report`, `health`, `common`. Sirven de frontera estable entre JSON y el dominio (`to_domain`, `Read` models).

---

## Frontend Streamlit (`streamlit_app/`)

- **`main.py`**: configuración de página, CSS, pestañas (citas, clientes, contratos, etc.) y enrutado por `st.query_params` (p. ej. `view=contract_sign`).
- **`api_client.py`**: funciones `get_*` / `post_*` / `put_*` / `patch_*` que encapsulan URLs y parsing de respuestas.
- **Módulos grandes de UI**: `citas_tab`, `customers_management` — lógica de formularios, sesión y llamadas API.
- **Contratos**: `contract_signing` (firma), `contract_read_view` (solo lectura), `contracts_admin` (plantillas Quill + tipos tattoo/piercing).

Las validaciones repetidas en formularios suelen estar en `validation.py` para no duplicar reglas entre pestañas.

---

## SQL (`sql/`)

Scripts numerados: esquema inicial `000_*`, cambios incrementales `00N_*`. El orden y notas operativas están en [sql/README.md](../sql/README.md).

---

## Flujo de datos típico

1. Usuario interactúa en Streamlit.
2. `api_client` envía HTTP a Litestar.
3. Controller valida y llama a `BusinessLogicService`.
4. Servicio usa repositorios y opcionalmente notificaciones.
5. Respuesta JSON vuelve a Streamlit y actualiza la UI.

---

## Dependencias principiales

- **Litestar**, **Uvicorn** — API asíncrona.
- **Pydantic** — esquemas y validación.
- **mysql-connector-python** — acceso a MySQL.
- **Streamlit**, **streamlit-drawable-canvas**, **streamlit-quill** — panel y componentes.
- **requests** — cliente HTTP en Streamlit.
- **python-dotenv** — variables de entorno.

---

## Ampliación recomendada

- Nuevos endpoints: esquema Pydantic → método en `BusinessLogicService` → SQL en repositorio → ruta en un controller (o uno nuevo).
- Nuevas pantallas: módulo en `streamlit_app/` + métodos en `api_client.py` si hacen falta rutas nuevas.
