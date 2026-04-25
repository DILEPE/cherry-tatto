import datetime
import requests


class NotificationService:
    """Servicio para comunicarse con el Webhook de n8n."""
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def notify(self, event: str, data: dict[str, object]) -> bool:
        payload = {
            "event": event,
            "data": data,
            "timestamp": datetime.datetime.now().isoformat()
        }
        try:
            # Enviamos la info a n8n
            response = requests.post(self.webhook_url, json=payload, timeout=5)
            return response.status_code == 200
        except Exception as e:
            print(f"Error enviando a n8n: {e}")
            return False