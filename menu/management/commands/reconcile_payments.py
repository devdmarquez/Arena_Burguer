from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from menu.mercadopago import PaymentError, check_config, sync_payment
from menu.models import PaymentAttempt


class Command(BaseCommand):
    help = "Consulta pagos pendientes y sincroniza estados verificados sin crear cobros."

    def add_arguments(self, parser):
        parser.add_argument("--order", type=int, help="Número de pedido para consultar.")
        parser.add_argument("--limit", type=int, default=20)

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= 100 or (options["order"] is not None and options["order"] < 1):
            raise CommandError("El límite debe estar entre 1 y 100 y el pedido debe ser positivo.")
        try:
            check_config()
        except PaymentError as exc:
            raise CommandError(str(exc)) from exc
        attempts = PaymentAttempt.objects.filter(environment=settings.MP_ENVIRONMENT,
                                                status__in=["created", "pending"],
                                                provider_order_id__isnull=False).order_by("created_at")
        if options["order"] is not None:
            attempts = attempts.filter(order_id=options["order"])
        count = 0
        for attempt in attempts[:options["limit"]]:
            try:
                result = sync_payment(attempt)
            except PaymentError as exc:
                raise CommandError(f"No se pudo consultar el pedido #{attempt.order_id}: {exc}") from exc
            self.stdout.write(f"Pedido #{attempt.order_id}: {result.get_status_display()}.")
            count += 1
        self.stdout.write(f"Intentos consultados: {count}. No se crearon cobros ni órdenes nuevas.")
