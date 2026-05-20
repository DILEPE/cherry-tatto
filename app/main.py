import logging
import os
from dotenv import load_dotenv
from litestar import Litestar
from litestar.config.cors import CORSConfig
from litestar.datastructures import State

# 1. Cargar las variables del archivo .env al entorno de Python
load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

# Importaciones de tus capas
from litestar.plugins.pydantic import PydanticPlugin

from app.infrastructure.database import DatabaseManager
from app.infrastructure.repositories import AppointmentRepository
from app.infrastructure.customer_repository import CustomerRepository
from app.infrastructure.panel_user_repository import PanelUserRepository
from app.infrastructure.external_api import NotificationService
from app.domain.services import BusinessLogicService
from app.application.appointment_controller import AppointmentController
from app.application.contract_controller import ContractController
from app.application.survey_controller import SurveyController
from app.application.survey_questions_controller import SurveyQuestionController
from app.application.template_controller import TemplateController
from app.application.customer_controller import CustomerController
from app.application.health_controller import HealthController
from app.application.panel_user_controller import PanelUserController


# 2. Extraer las variables del entorno usando os.getenv()
# El segundo parámetro es un valor por defecto si la variable no existe en el .env
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME", "inkmanager_db")
N8N_URL = os.getenv("N8N_WEBHOOK_URL")
# Webhook dedicado para PDF de abonos (event payment_receipt_pdf). Si no está definido, usa N8N_WEBHOOK_URL.
# Modo envío `payment_receipt_pdf`: multipart por defecto (WhatsApp / binario «data» en n8n).
# Solo JSON con pdf_base64: N8N_PAYMENT_RECEIPT_TRANSPORT=json
N8N_RECEIPT_WEBHOOK_URL = os.getenv("N8N_RECEIPT_WEBHOOK_URL")
# Webhook para PDF de consentimiento por procedimiento (event contract_consent_pdf). Si no está definido,
# se usa N8N_RECEIPT_WEBHOOK_URL y luego N8N_WEBHOOK_URL.
N8N_CONTRACT_CONSENT_WEBHOOK_URL = os.getenv("N8N_CONTRACT_CONSENT_WEBHOOK_URL")
# Opcional — GET /health/n8n: sondeo al endpoint de status (toma prioridad si está definido).
# Ej.: N8N_STATUS_URL=http://localhost:5678/webhook-test/cherry-tatto/status
APP_PORT = int(os.getenv("PORT", 5000))
IS_DEBUG = os.getenv("DEBUG", "True").lower() == "true"

# 3. Pasar las variables a las clases de Infraestructura
# Aquí las variables del .env entran a los constructores (__init__) de tus clases
db_mgr = DatabaseManager(
    host=DB_HOST, 
    user=DB_USER, 
    password=DB_PASS, 
    database=DB_NAME
)
db_mgr.ensure_appointment_date_datetime()
db_mgr.ensure_appointment_is_priority_column()
db_mgr.ensure_appointment_payment_paid_on_column()

repo = AppointmentRepository(db_mgr)
customer_repo = CustomerRepository(db_mgr)
panel_user_repo = PanelUserRepository(db_mgr)

notifier = NotificationService(
    webhook_url=N8N_URL,
    receipt_webhook_url=N8N_RECEIPT_WEBHOOK_URL,
    contract_consent_webhook_url=N8N_CONTRACT_CONSENT_WEBHOOK_URL,
)

# 4. Inicializar Servicio de Dominio
business_service = BusinessLogicService(repo, customer_repo, notifier, panel_user_repo)

# 5. Configurar Litestar
initial_state = State({"service": business_service})

app = Litestar(
    route_handlers=[
        HealthController,
        AppointmentController,
        ContractController,
        TemplateController,
        SurveyController,
        SurveyQuestionController,
        CustomerController,
        PanelUserController,
    ],
    plugins=[PydanticPlugin()],
    cors_config=CORSConfig(allow_origins=["*"]),
    state=initial_state,
    debug=IS_DEBUG,
)

# Arranque (desde la raíz del repo, con venv activo):
#   python -m uvicorn app.main:app --host 127.0.0.1 --port 5000
# El puerto lo toma de la variable PORT en .env (por defecto 5000).