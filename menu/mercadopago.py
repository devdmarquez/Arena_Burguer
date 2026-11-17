"""Checkout Pro vía Orders API. Nunca acepta importes del navegador."""
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils.dateparse import parse_datetime

from .models import Order, PaymentAttempt


class PaymentError(ValueError):
    pass


def check_config():
    required = (settings.MP_ACCESS_TOKEN, settings.MP_WEBHOOK_SECRET, settings.MP_SELLER_ID,
                settings.MP_APPLICATION_ID, settings.MP_PUBLIC_BASE_URL)
    base = urlsplit(settings.MP_PUBLIC_BASE_URL)
    if (not settings.MP_ENABLED or not all(required) or settings.MP_ENVIRONMENT not in ("test", "production")
            or base.scheme != "https" or not base.hostname or base.username or base.query or base.fragment or base.path):
        raise PaymentError("El pago online todavía no está configurado. No se realizó ningún cobro.")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def api(method, path, payload=None, key=None):
    check_config()
    headers = {"Authorization": "Bearer " + settings.MP_ACCESS_TOKEN,
               "Content-Type": "application/json", "Accept": "application/json"}
    if key:
        headers["X-Idempotency-Key"] = str(key)
    request = Request("https://api.mercadopago.com" + path,
                      data=json.dumps(payload).encode() if payload is not None else None,
                      headers=headers, method=method)
    try:
        with build_opener(NoRedirect).open(request, timeout=12) as response:
            result = json.load(response)
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        # No exponer cuerpos del proveedor, secretos o datos del comprador en la respuesta.
        raise PaymentError("No pudimos comunicarnos con Mercado Pago. Podés volver a intentar con el mismo pedido.") from exc


def validate_resource(resource, attempt):
    try:
        matches = (str(resource["external_reference"]) == str(attempt.pk)
                   and Decimal(str(resource["total_amount"])) == Decimal(attempt.amount)
                   and resource.get("currency") == "ARS"
                   and str(resource.get("user_id")) == settings.MP_SELLER_ID
                   and str(resource.get("integration_data", {}).get("application_id")) == settings.MP_APPLICATION_ID)
    except (KeyError, InvalidOperation, TypeError):
        matches = False
    if not matches:
        raise PaymentError("El pago recibido no coincide con el pedido o la cuenta configurada.")


def start_payment(order):
    check_config()
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        if locked.status == "cancelled" or locked.payment_status in ("paid", "refunded", "review"):
            raise PaymentError("Este pedido no admite un nuevo pago.")
        if locked.total is None or locked.total < 1:
            raise PaymentError("El pedido todavía no tiene un total definitivo.")
        latest = locked.payment_attempts.first()
        if latest and latest.environment != settings.MP_ENVIRONMENT:
            raise PaymentError("Este pedido pertenece a otro entorno de pagos. Creá un pedido nuevo.")
        if latest and latest.status in ("created", "pending"):
            attempt = latest
        else:
            attempt = PaymentAttempt.objects.create(order=locked, amount=locked.total, environment=settings.MP_ENVIRONMENT)
            locked.payment_status = "pending"
            locked.save(update_fields=["payment_status"])
    # El intento ya quedó guardado. Un timeout reutiliza la misma clave, sin crear otro cobro.
    with transaction.atomic():
        attempt = PaymentAttempt.objects.select_for_update().select_related("order").get(pk=attempt.pk)
        if attempt.checkout_url:
            return attempt
        return_url = settings.MP_PUBLIC_BASE_URL + reverse("payment_return", args=[attempt.pk])
        items = [{"title": item.product_name, "quantity": item.quantity, "unit_price": f"{item.unit_price:.2f}"}
                 for item in attempt.order.items.all()]
        if attempt.order.delivery_fee:
            items.append({"title": "Envío", "quantity": 1, "unit_price": f"{attempt.order.delivery_fee:.2f}"})
        if sum(Decimal(item["unit_price"]) * item["quantity"] for item in items) != attempt.amount:
            raise PaymentError("El detalle del pedido no coincide con su total.")
        resource = api("POST", "/v1/orders", {
            "type": "online", "processing_mode": "manual", "capture_mode": settings.MP_CAPTURE_MODE,
            "total_amount": f"{attempt.amount:.2f}", "external_reference": str(attempt.pk),
            "items": items, "expiration_time": "PT1H",
            "config": {"online": {"success_url": return_url, "failure_url": return_url,
                                  "pending_url": return_url, "auto_return": "all"}},
        }, key=attempt.pk)
        validate_resource(resource, attempt)
        provider_id = str(resource.get("id", ""))
        link = resource.get("checkout_url", "")
        url = urlsplit(link)
        if (not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", provider_id) or url.scheme != "https"
                or url.hostname != "www.mercadopago.com.ar" or url.username):
            raise PaymentError("Mercado Pago no devolvió un enlace de pago válido.")
        if (settings.MP_ENVIRONMENT == "test") != provider_id.startswith("ORDTST"):
            raise PaymentError("El recurso recibido no corresponde al entorno de pagos configurado.")
        attempt.provider_order_id = provider_id
        attempt.checkout_url = link
        attempt.status = "pending"
        attempt.save(update_fields=["provider_order_id", "checkout_url", "status", "updated_at"])
        return attempt


def verify_signature(request):
    secret = settings.MP_WEBHOOK_SECRET
    resource_id = request.GET.get("data.id", "")
    request_id = request.headers.get("x-request-id", "")
    if not secret or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", resource_id) or not request_id or len(request_id) > 200:
        return False
    try:
        parts = dict(part.strip().split("=", 1) for part in request.headers.get("x-signature", "").split(","))
        timestamp, signature = parts["ts"], parts["v1"]
        seconds = int(timestamp) / (1000 if len(timestamp) > 10 else 1)
        if abs(time.time() - seconds) > 300:
            return False
    except (ValueError, KeyError):
        return False
    manifest = f"id:{resource_id.lower()};request-id:{request_id};ts:{timestamp};"
    expected = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def sync_payment(attempt):
    if attempt.environment != settings.MP_ENVIRONMENT or not attempt.provider_order_id:
        raise PaymentError("No se puede consultar este intento en el entorno actual.")
    resource = api("GET", "/v1/orders/" + attempt.provider_order_id)
    validate_resource(resource, attempt)
    if resource.get("id") != attempt.provider_order_id:
        raise PaymentError("La respuesta no corresponde al pago consultado.")
    updated = parse_datetime(resource.get("last_updated_date", ""))
    if not updated or updated.tzinfo is None:
        raise PaymentError("El pago no tiene una fecha de actualización válida.")
    status = resource.get("status")
    mapping = {"created": "pending", "processing": "pending", "action_required": "pending",
               "failed": "failed", "canceled": "cancelled", "expired": "cancelled", "refunded": "refunded"}
    if status == "processed":
        try:
            paid = Decimal(str(resource.get("total_paid_amount", "0")))
        except InvalidOperation as exc:
            raise PaymentError("El importe pagado no es válido.") from exc
        next_status = "paid" if paid == attempt.amount and resource.get("status_detail") == "accredited" else "review"
    elif status in mapping:
        next_status = mapping[status]
    else:
        next_status = "review"
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=attempt.order_id)
        current = PaymentAttempt.objects.select_for_update().get(pk=attempt.pk)
        if current.provider_updated_at and updated <= current.provider_updated_at:
            return current
        current.status, current.provider_status, current.provider_updated_at = next_status, str(status), updated
        current.save(update_fields=["status", "provider_status", "provider_updated_at", "updated_at"])
        states = list(order.payment_attempts.values_list("status", flat=True))
        if states.count("paid") > 1 or ("paid" in states and "refunded" in states):
            order.payment_status = "review"
        elif "paid" in states:
            order.payment_status = "paid"
        elif "review" in states:
            order.payment_status = "review"
        elif "refunded" in states:
            order.payment_status = "refunded"
        elif any(state in ("pending", "created") for state in states):
            order.payment_status = "pending"
        else:
            order.payment_status = next_status
        order.save(update_fields=["payment_status"])
        return current
