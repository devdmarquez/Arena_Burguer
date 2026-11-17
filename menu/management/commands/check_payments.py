from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse

from menu.mercadopago import PaymentError, check_config


class Command(BaseCommand):
    help = "Comprueba la configuración de pagos sin mostrar secretos ni llamar a Mercado Pago."

    def handle(self, *args, **options):
        required = ("MP_ACCESS_TOKEN", "MP_WEBHOOK_SECRET", "MP_SELLER_ID", "MP_APPLICATION_ID", "MP_PUBLIC_BASE_URL")
        missing = [name for name in required if not getattr(settings, name)]
        self.stdout.write("Pagos: " + ("activados" if settings.MP_ENABLED else "desactivados"))
        self.stdout.write("Entorno: " + settings.MP_ENVIRONMENT)
        if missing:
            raise CommandError("Falta completar en .env: " + ", ".join(missing) + ". No compartas esos valores en el chat.")
        try:
            check_config()
        except PaymentError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write("URL de notificaciones: " + settings.MP_PUBLIC_BASE_URL + reverse("payment_webhook"))
        self.stdout.write(self.style.SUCCESS("Configuración local completa. Aún falta probar la conexión y los pagos reales del entorno de prueba."))
