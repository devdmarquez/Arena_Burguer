from django.conf import settings
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import ensure_csrf_cookie
import json
from hashlib import sha256
from uuid import uuid4
from django.db import transaction
from django.urls import reverse
from .forms import CheckoutForm

from .cart import CartError, normalize, quantity, summary

from .models import Aderezo, Burger, Extra, Product, Order, OrderItem, AboutPhoto


@ensure_csrf_cookie
def index(request):
    if not request.session.get("checkout_token"):
        request.session["checkout_token"] = str(uuid4())
    burgers = Burger.objects.filter(available=True)
    aderezos = Aderezo.objects.filter(available=True)
    extras = Extra.objects.filter(available=True)
    products = Product.objects.filter(available=True, price__gt=0)
    product_groups = [
        {"id": "papas", "label": "Papas", "title": "Papas y acompañamientos",
         "description": "Algo más para compartir o sumar a tu hamburguesa.",
         "items": [p for p in products if p.category == Product.Category.SIDE]},
        {"id": "bebidas", "label": "Bebidas", "title": "Bebidas",
         "description": "Elegí con qué acompañar tu pedido.",
         "items": [p for p in products if p.category == Product.Category.DRINK]},
    ]
    product_groups = [group for group in product_groups if group["items"]]

    # Datos que usa el JavaScript del pedido (se inyectan con json_script)
    data = {
        "burgers": {
            str(b.id): {"id": b.id, "name": b.name, "desc": b.description, "price": b.sale_price,
                        "original_price": b.price, "discount_percent": b.discount_percent if b.has_discount else 0}
            for b in burgers
        },
        "aderezos": [{"id": a.pk, "name": a.name} for a in aderezos],
        "extras": [{"id": e.pk, "name": e.name, "price": e.sale_price,
                    "original_price": e.price, "discount_percent": e.discount_percent if e.has_discount else 0} for e in extras],
        "cart": summary(request.session),
        "shipping": {"fixed_fee": settings.DELIVERY_FIXED_FEE, "address": settings.STORE_ADDRESS},
        "payments_enabled": settings.MP_ENABLED,
    }
    script = settings.BASE_DIR / "menu" / "static" / "menu" / "app.js"
    motion = settings.BASE_DIR / "menu" / "static" / "menu" / "motion.css"
    app_version = sha256(script.read_bytes() + motion.read_bytes()).hexdigest()[:12]
    return render(request, "menu/index.html", {
        "burgers": burgers, "products": products, "product_groups": product_groups,
        "data": data, "app_version": app_version,
        "whatsapp_number": settings.WHATSAPP_NUMBER,
    })


@require_http_methods(["GET"])
def about(request):
    motion = settings.BASE_DIR / "menu" / "static" / "menu" / "motion.css"
    return render(request, "menu/about.html", {
        "about_photos": AboutPhoto.objects.filter(active=True)[:6],
        "whatsapp_number": settings.WHATSAPP_NUMBER,
        "store_address": settings.STORE_ADDRESS,
        "app_version": sha256(motion.read_bytes()).hexdigest()[:12],
    })


@require_http_methods(["GET", "POST"])
def cart(request):
    if request.method == "GET":
        return JsonResponse(summary(request.session))
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise CartError("El pedido no es válido.")
        items = dict(request.session.get("cart", {}))
        action = data.get("action")
        if action == "add":
            item = normalize(data)
            if len(items) >= 50:
                raise CartError("El carrito admite hasta 50 renglones.")
            items[uuid4().hex] = item
        elif action in ("quantity", "remove"):
            key = data.get("id")
            if not isinstance(key, str) or key not in items:
                raise CartError("El producto ya no está en el carrito.")
            if action == "remove":
                del items[key]
            else:
                items[key] = normalize({**items[key], "qty": quantity(data.get("qty"))})
        elif action == "clear":
            items = {}
        else:
            raise CartError("La acción no es válida.")
        request.session["cart"] = items
        request.session["checkout_token"] = str(uuid4())
        return JsonResponse(summary(request.session))
    except (CartError, ValueError, UnicodeDecodeError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)


def order_response(order):
    return JsonResponse({"number": order.pk, "products_total": order.products_total,
                         "delivery_fee": order.delivery_fee, "total": order.total,
                         "payment_status": order.payment_status,
                         "payment_start_url": reverse("payment_start", args=[order.checkout_token]) if settings.MP_ENABLED else None})


@require_http_methods(["POST"])
def checkout(request):
    if settings.MP_ENABLED:
        from .mercadopago import check_config, PaymentError
        try:
            check_config()
        except PaymentError as exc:
            return JsonResponse({"error": str(exc)}, status=503)
    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Los datos no son válidos."}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({"error": "Los datos no son válidos."}, status=400)
    token = data.get("checkout_token")
    allowed = [request.session.get("checkout_token"), request.session.get("last_order_token")]
    if not isinstance(token, str) or not token or token not in allowed:
        return JsonResponse({"error": "El carrito cambió. Volvé a revisarlo."}, status=409)
    existing = Order.objects.filter(checkout_token=token).first()
    if existing:
        return order_response(existing)
    form = CheckoutForm(data)
    if not form.is_valid():
        return JsonResponse({"error": "Revisá los datos del pedido.", "fields": form.errors}, status=400)
    customer = form.cleaned_data
    fee = settings.DELIVERY_FIXED_FEE if customer["fulfillment"] == Order.Fulfillment.DELIVERY else 0
    with transaction.atomic():
        # Mantener precios y disponibilidad estables durante la creación.
        list(Burger.objects.select_for_update().order_by("pk"))
        list(Extra.objects.select_for_update().order_by("pk"))
        list(Aderezo.objects.select_for_update().order_by("pk"))
        list(Product.objects.select_for_update().order_by("pk"))
        current = summary(request.session)
        if not current["can_continue"]:
            return JsonResponse({"error": "El carrito está vacío o tiene productos no disponibles."}, status=409)
        if type(data.get("products_total")) is not int or data["products_total"] != current["total"]:
            return JsonResponse({"error": "Los precios cambiaron. Volvé al carrito para revisar el total."}, status=409)
        order, created = Order.objects.get_or_create(checkout_token=token, defaults={
            "customer_name": customer["name"], "phone": customer["phone"],
            "fulfillment": customer["fulfillment"], "address": customer["address"],
            "locality": customer["locality"], "reference": customer["reference"], "products_total": current["total"],
            "delivery_fee": fee, "total": current["total"] + fee,
        })
        if created:
            OrderItem.objects.bulk_create([OrderItem(
                order=order, burger_id=item["burger_id"], product_id=item.get("product_id"), product_name=item["name"],
                quantity=item["qty"], unit_price=item["unit_price"], subtotal=item["subtotal"],
                aderezos=item["aderezo_names"], extras=item["extra_details"], notes=item["notes"],
            ) for item in current["items"]])
    request.session["cart"] = {}
    request.session["last_order_token"] = token
    request.session["checkout_token"] = str(uuid4())
    return order_response(order)
