import json

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .mercadopago import PaymentError, start_payment, sync_payment, verify_signature
from .models import Order, PaymentAttempt


def owns_order(request, order):
    return str(order.checkout_token) in (
        request.session.get("checkout_token"), request.session.get("last_order_token"),
    )


@never_cache
@require_POST
def start(request, token):
    order = get_object_or_404(Order, checkout_token=token)
    if not owns_order(request, order):
        return JsonResponse({"error": "Este pedido no pertenece a tu sesión."}, status=403)
    try:
        attempt = start_payment(order)
        return JsonResponse({"checkout_url": attempt.checkout_url})
    except PaymentError as exc:
        return JsonResponse({"error": str(exc)}, status=503)


@never_cache
@require_GET
def returned(request, attempt_id):
    attempt = get_object_or_404(PaymentAttempt.objects.select_related("order"), pk=attempt_id)
    if not owns_order(request, attempt.order):
        return HttpResponse("No tenés acceso a este pedido desde esta sesión.", status=403)
    # Los parámetros de la URL del comprador nunca prueban que hubo un pago.
    return render(request, "menu/payment_return.html", {"attempt": attempt, "order": attempt.order})


@never_cache
@require_POST
def refresh(request, attempt_id):
    attempt = get_object_or_404(PaymentAttempt.objects.select_related("order"), pk=attempt_id)
    if not owns_order(request, attempt.order):
        return HttpResponse(status=403)
    error = ""
    try:
        attempt = sync_payment(attempt)
    except PaymentError as exc:
        error = str(exc)
    attempt.order.refresh_from_db()
    return render(request, "menu/payment_return.html", {"attempt": attempt, "order": attempt.order, "error": error})


@csrf_exempt
@require_POST
def webhook(request):
    if not settings.MP_ENABLED or not settings.MP_WEBHOOK_SECRET:
        return HttpResponse(status=503)
    if not verify_signature(request):
        return HttpResponse(status=401)
    try:
        event = json.loads(request.body)
        if not isinstance(event, dict) or event.get("type") != "order":
            return HttpResponse(status=200)
        if event.get("live_mode") is not (settings.MP_ENVIRONMENT == "production"):
            return HttpResponse(status=400)
        if str(event.get("data", {}).get("id", "")).lower() != request.GET["data.id"].lower():
            return HttpResponse(status=400)
    except (ValueError, AttributeError):
        return HttpResponse(status=400)
    attempt = PaymentAttempt.objects.filter(provider_order_id__iexact=request.GET["data.id"]).first()
    if not attempt:
        return HttpResponse(status=200)
    try:
        sync_payment(attempt)
    except PaymentError:
        # Un fallo transitorio debe provocar un reintento del proveedor.
        return HttpResponse(status=503)
    return HttpResponse(status=200)
