import json

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import Burger, Extra, Product, Order


class DiscountTests(TestCase):
    def test_validation_rounding_and_disabled_offer(self):
        for model in (Burger, Extra, Product):
            item = model(price=2501, discount_active=True, discount_percent=10)
            self.assertEqual(item.sale_price, 2251)
            item.discount_active = False
            self.assertEqual(item.sale_price, 2501)
            item.discount_active, item.discount_percent = True, 0
            with self.assertRaises(ValidationError):
                item.clean()
        item = Product(price=None, discount_active=True, discount_percent=20)
        with self.assertRaises(ValidationError):
            item.clean()

    def test_discount_is_used_in_cart_order_and_snapshots(self):
        burger = Burger.objects.create(name="Oferta", description="Carne", price=8000,
                                       discount_active=True, discount_percent=20)
        extra = Extra.objects.create(name="Extra", price=1000)
        side = Product.objects.create(name="Acompañamiento", category="side", available=True,
                                       price=12000, discount_active=True, discount_percent=25)
        drink = Product.objects.create(name="Bebida", category="drink", available=True,
                                       price=2500, suggested=True, discount_active=True, discount_percent=10)
        page = self.client.get(reverse("index"))
        self.assertContains(page, '<del>$8000</del>', html=True)
        self.assertNotContains(page, 'id="combos"')
        self.assertEqual(page.context["data"]["burgers"][str(burger.pk)]["price"], 6400)
        self.client.post(reverse("cart"), json.dumps({"action": "add", "burger_id": burger.pk,
            "qty": 2, "extras": [extra.pk], "price": 1}), content_type="application/json")
        cart = self.client.post(reverse("cart"), json.dumps({"action": "add", "product_type": "product",
            "product_id": side.pk, "qty": 1}), content_type="application/json").json()
        self.assertEqual(cart["total"], 23800)
        suggestion = next(p for p in cart["suggestions"] if p["id"] == drink.pk)
        self.assertEqual(suggestion["price"], 2250)
        self.assertEqual(suggestion["original_price"], drink.price)
        response = self.client.post(reverse("checkout"), json.dumps({"checkout_token": cart["checkout_token"],
            "products_total": cart["total"], "name": "Cliente", "phone": "1155551234", "fulfillment": "pickup"}),
            content_type="application/json")
        self.assertEqual(response.status_code, 200)
        order = Order.objects.get(pk=response.json()["number"])
        self.assertEqual(order.total, 23800)
        burger.discount_active = False
        burger.save()
        order.refresh_from_db()
        self.assertEqual(order.items.get(burger=burger).unit_price, 7400)
        self.assertEqual(order.total, 23800)

    def test_cart_reprices_when_discount_changes(self):
        side = Product.objects.create(name="Papas", category="side", available=True, price=5000)
        self.client.post(reverse("cart"), json.dumps({"action": "add", "product_type": "product",
            "product_id": side.pk, "qty": 1}), content_type="application/json")
        side.discount_active, side.discount_percent = True, 20
        side.save()
        self.assertEqual(self.client.get(reverse("cart")).json()["total"], 4000)
