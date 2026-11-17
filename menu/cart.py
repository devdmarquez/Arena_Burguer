"""Carrito en sesión. Los precios siempre se consultan en la base."""
from .models import Aderezo, Burger, Extra, Product


class CartError(ValueError):
    pass


def quantity(value):
    if type(value) is not int or not 1 <= value <= 99:
        raise CartError("La cantidad debe estar entre 1 y 99.")
    return value


def selection(model, ids):
    if not isinstance(ids, list) or any(type(pk) is not int for pk in ids):
        raise CartError("La selección no es válida.")
    objects = list(model.objects.filter(pk__in=ids, available=True).order_by("pk"))
    if len(objects) != len(set(ids)):
        raise CartError("Un aderezo o extra ya no está disponible. Revisá tu selección.")
    return objects


def normalize(data):
    if data.get("product_type") == "product":
        if type(data.get("product_id")) is not int:
            raise CartError("Elegí un producto válido.")
        product = Product.objects.filter(pk=data["product_id"], available=True, price__gt=0).first()
        if product is None:
            raise CartError("Este producto ya no está disponible o no tiene precio.")
        if data.get("aderezos") or data.get("extras"):
            raise CartError("Los aderezos y extras se eligen para las hamburguesas.")
        return {"product_type": "product", "product_id": product.pk, "burger_id": None,
                "qty": quantity(data.get("qty")), "aderezos": [], "extras": [], "notes": ""}
    if data.get("product_type", "burger") != "burger":
        raise CartError("El tipo de producto no es válido.")
    if type(data.get("burger_id")) is not int:
        raise CartError("Elegí una hamburguesa válida.")
    burger = Burger.objects.filter(pk=data["burger_id"], available=True).first()
    if burger is None:
        raise CartError("Esta hamburguesa ya no está disponible.")
    aderezos = selection(Aderezo, data.get("aderezos", []))
    extras = selection(Extra, data.get("extras", []))
    notes = data.get("notes", "")
    if not isinstance(notes, str) or len(notes) > 500:
        raise CartError("Las aclaraciones deben tener hasta 500 caracteres.")
    return {
        "burger_id": burger.pk,
        "qty": quantity(data.get("qty")),
        "aderezos": [a.pk for a in aderezos],
        "extras": [e.pk for e in extras],
        "notes": notes.strip(),
    }


def summary(session):
    items = []
    for key, stored in session.get("cart", {}).items():
        try:
            data = normalize(stored)
        except CartError as exc:
            items.append({"id": key, "qty": stored["qty"], "available": False,
                          "error": str(exc), "name": "Producto no disponible"})
            continue
        is_product = data.get("product_type") == "product"
        burger = Product.objects.get(pk=data["product_id"]) if is_product else Burger.objects.get(pk=data["burger_id"])
        extras = list(Extra.objects.filter(pk__in=data["extras"]).order_by("pk"))
        price = burger.sale_price + sum(e.sale_price for e in extras)
        items.append({**data, "product_type": "product" if is_product else "burger", "id": key, "available": True, "name": burger.name,
                      "aderezo_names": list(Aderezo.objects.filter(pk__in=data["aderezos"]).order_by("pk").values_list("name", flat=True)),
                      "extra_names": [e.name for e in extras],
                      "extra_details": [{"name": e.name, "price": e.sale_price} for e in extras],
                      "unit_price": price, "subtotal": price * data["qty"]})
    included = [item["product_id"] for item in items if item.get("product_type") == "product"]
    suggestions = Product.objects.filter(available=True, price__gt=0, suggested=True).exclude(pk__in=included)[:3]
    return {"items": items, "checkout_token": session.get("checkout_token"),
            "suggestions": [{"id": p.pk, "name": p.name, "description": p.description,
                             "category": p.get_category_display(), "price": p.sale_price,
                             "original_price": p.price, "discount_percent": p.discount_percent if p.has_discount else 0,
                             "photo": p.photo.url if p.photo else ""} for p in suggestions],
            "count": sum(i["qty"] for i in items),
            "total": sum(i.get("subtotal", 0) for i in items),
            "can_continue": bool(items) and all(i["available"] for i in items)}
