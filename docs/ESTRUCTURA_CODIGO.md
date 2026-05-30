# Estructura interna del código

Este documento describe cómo está organizado el repositorio **cherry_tattoo** a nivel de módulos y responsabilidades. Complementa el [README principal](../README.md) (instalación y visión general).

## Principio general

El backend sigue una separación en capas inspirada en **hexagonal / limpia**:

1. **Dominio** — reglas de negocio y modelos lógicos (sin detalles de HTTP ni SQL).
2. **Aplicación** — controladores HTTP (Litestar): entrada/salida, códigos, validación Pydantic.
3. **Infraestructura** — MySQL, repositorios, integraciones externas (p. ej. n8n).
4. **Esquemas (Pydantic)** — contratos de API: request/response compartidos con validación.

El **panel Angular** (`cherry_tattoo_angular`) es el cliente HTTP; no persiste datos fuera de la API.

```
app/
├── main.py                 # Punto de entrada Litestar, wiring DI manual, CORS
├── application/            # Controllers (rutas HTTP)
├── domain/                 # Servicios de negocio, modelos dataclass, utilidades de dominio
├── infrastructure/         # DB, repositorios SQL, notificaciones
├── schemas/                # Pydantic: DTOs de API
├── assets/                 # Logos Rock City, plantillas HTML, PDFs, flujos n8n
└── types/                  # Tipos auxiliares (p. ej. JSON)
```

---

## Backend (`app/`)

### `app/main.py`

- Carga `.env` con `python-dotenv`.
- Instancia `DatabaseManager`, repositorios, `NotificationService` y `BusinessLogicService`.
- Registra controladores en `Litestar` y expone `app` para Uvicorn.

### `app/application/*_controller.py`

Cada controlador agrupa rutas bajo un prefijo (p. ej. `/api/appointments`). Responsabilidades típicas:

- Recibir cuerpos/query ya validados por Pydantic (donde aplica).
- Invocar métodos asíncronos de `BusinessLogicService` vía `state.service`.
- Traducir excepciones a `HTTPException`.

Archivos habituales: `appointment_controller`, `customer_controller`, `contract_controller`, `template_controller`, `survey_controller`, `survey_questions_controller`, `panel_user_controller`, `health_controller`.

### `app/domain/`

| Módulo | Contenido |
|--------|-----------|
| `services.py` | `BusinessLogicService`: orquestación de casos de uso. |
| `models.py` | Dataclasses de entrada/salida del dominio. |
| `service_types.py` | Resolución de texto de servicio → valor almacenado en cita. |
| `contract_kinds.py` | Mapeo cita → tipo de plantilla (`tattoo` / `piercing`). |
| `survey_question_helpers.py` | Etiquetas de preguntas de encuesta (p. ej. `{service_type}`). |
| `payment_receipt_pdf.py` | Generación de PDF de recibos (assets en `app/assets/`). |

### `app/infrastructure/`

| Módulo | Contenido |
|--------|-----------|
| `database.py` | `DatabaseManager`: conexión MySQL. |
| `repositories.py` | Citas, contratos, plantillas, reportes. |
| `customer_repository.py` | Persistencia de clientes. |
| `external_api.py` | Webhooks n8n. |

### `app/schemas/`

Modelos Pydantic v2 por contexto: `appointment`, `customer`, `contract`, `template`, `survey`, `panel_user`, `report`, `health`, `common`.

---

## Panel Angular (repositorio aparte)

- Repositorio: **`cherry_tattoo_angular`** (desarrollo principal).
- Copia opcional en este repo: `panel-frontend/`.
- Consume la misma API REST; autenticación vía `POST /api/panel-users/login`.

---

## SQL (`sql/`)

Scripts numerados: esquema inicial `000_*`, cambios incrementales `00N_*`. Orden en [sql/README.md](../sql/README.md).

---

## Flujo de datos típico

1. Usuario interactúa en el panel Angular.
2. El frontend envía HTTP a Litestar.
3. Controller valida y llama a `BusinessLogicService`.
4. Servicio usa repositorios y opcionalmente notificaciones.
5. Respuesta JSON actualiza la UI.

---

## Dependencias principales (Python)

- **Litestar**, **Uvicorn** — API.
- **Pydantic** — esquemas y validación.
- **mysql-connector-python** — MySQL.
- **python-dotenv** — variables de entorno.
- **pymupdf**, **pillow** — PDF de recibos e iconos.

---

## Ampliación recomendada

- Nuevos endpoints: esquema Pydantic → `BusinessLogicService` → repositorio → controller.
- Nuevas pantallas: módulo en `cherry_tattoo_angular` + servicios HTTP del feature.
