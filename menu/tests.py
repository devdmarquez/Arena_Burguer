import json

from django.test import Client, TestCase
from django.test import override_settings
from django.urls import reverse

from .models import Aderezo, Burger, Extra, Product, Order


class CartTests(TestCase):
    def setUp(self):
        self.burger = Burger.objects.create(name="Prueba", description="Carne", price=8000)
        self.extra = Extra.objects.create(name="Extra de prueba", price=700)
        self.sauce = Aderezo.objects.create(name="Salsa de prueba")
        self.url = reverse("cart")

    def post(self, **payload):
        return self.client.post(self.url, json.dumps(payload), content_type="application/json")

    def add(self, **overrides):
        payload = {"action": "add", "burger_id": self.burger.pk, "qty": 2,
                   "aderezos": [self.sauce.pk], "extras": [self.extra.pk], "notes": "Sin sal"}
        return self.post(**(payload | overrides))

    def test_multiple_customizations_persist_and_are_private(self):
        self.add()
        result = self.add(extras=[], qty=1).json()
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(result["count"], 3)
        self.assertEqual(result["total"], 25400)
        self.client.get(reverse("index"))
        self.assertEqual(self.client.get(self.url).json(), result)
        self.assertEqual(Client().get(self.url).json()["items"], [])

    def test_prices_are_calculated_on_server_and_refreshed(self):
        result = self.add(price=1, unit_price=1, subtotal=1).json()
        self.assertEqual(result["total"], 17400)
        self.extra.price = 1000
        self.extra.save()
        self.assertEqual(self.client.get(self.url).json()["total"], 18000)

    def test_quantity_remove_and_clear(self):
        key = self.add().json()["items"][0]["id"]
        result = self.post(action="quantity", id=key, qty=3).json()
        self.assertEqual(result["total"], 26100)
        result = self.post(action="remove", id=key).json()
        self.assertFalse(result["can_continue"])
        self.add()
        self.assertEqual(self.post(action="clear").json()["count"], 0)

    def test_invalid_input_does_not_change_cart(self):
        for payload in ({"qty": 0}, {"qty": True}, {"qty": 100}, {"qty": "2"},
                        {"burger_id": -1}, {"extras": [-1]}, {"aderezos": "bad"},
                        {"notes": "x" * 501}):
            with self.subTest(payload=payload):
                self.assertEqual(self.add(**payload).status_code, 400)
        self.assertEqual(self.client.get(self.url).json()["items"], [])
        self.assertEqual(self.client.post(self.url, "[]", content_type="application/json").status_code, 400)
        self.assertEqual(self.client.post(self.url, "{", content_type="application/json").status_code, 400)

    def test_unavailable_item_blocks_continuation_and_can_be_removed(self):
        key = self.add().json()["items"][0]["id"]
        self.extra.available = False
        self.extra.save()
        result = self.client.get(self.url).json()
        self.assertFalse(result["can_continue"])
        self.assertFalse(result["items"][0]["available"])
        self.assertEqual(self.add().status_code, 400)
        self.assertEqual(self.post(action="remove", id=key).json()["items"], [])

    def test_csrf_protection_and_method_restriction(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(self.url, "{}", content_type="application/json").status_code, 403)
        page = client.get(reverse("index"))
        self.assertContains(page, "cart-button")
        self.assertContains(page, "csrfmiddlewaretoken")
        token = client.cookies["csrftoken"].value
        response = client.post(self.url, json.dumps({"action": "clear"}),
                               content_type="application/json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.delete(self.url).status_code, 405)


class CheckoutTests(TestCase):
    def setUp(self):
        self.burger = Burger.objects.create(name="Pedido prueba", description="Carne", price=8000)
        self.extra = Extra.objects.create(name="Cheddar prueba", price=700)
        self.sauce = Aderezo.objects.create(name="Salsa prueba")
        cart = self.client.post(reverse("cart"), json.dumps({
            "action": "add", "burger_id": self.burger.pk, "qty": 2,
            "aderezos": [self.sauce.pk], "extras": [self.extra.pk], "notes": "Sin sal",
        }), content_type="application/json").json()
        self.payload = {"checkout_token": cart["checkout_token"], "products_total": cart["total"],
                        "name": "Cliente prueba", "phone": "11 5555 1234", "fulfillment": "pickup"}

    def submit(self, **overrides):
        return self.client.post(reverse("checkout"), json.dumps(self.payload | overrides),
                                content_type="application/json")

    def test_pickup_saves_snapshot_and_clears_cart(self):
        response = self.submit(total=1, payment_status="paid", address="No guardar")
        self.assertEqual(response.status_code, 200)
        order = Order.objects.get(pk=response.json()["number"])
        self.assertEqual(order.products_total, 17400)
        self.assertEqual(order.total, 17400)
        self.assertEqual(order.delivery_fee, 0)
        self.assertEqual(order.payment_status, "pending")
        self.assertEqual(order.address, "")
        item = order.items.get()
        self.assertEqual(item.aderezos, ["Salsa prueba"])
        self.assertEqual(item.extras, [{"name": "Cheddar prueba", "price": 700}])
        self.assertEqual(item.notes, "Sin sal")
        self.burger.price = 9999
        self.burger.save()
        self.burger.delete()
        self.extra.delete()
        item.refresh_from_db()
        self.assertIsNone(item.burger_id)
        self.assertEqual(item.unit_price, 8700)
        self.assertEqual(item.product_name, "Pedido prueba")
        self.assertEqual(self.client.get(reverse("cart")).json()["items"], [])

    def test_delivery_requires_address_and_locality(self):
        self.assertEqual(self.submit(fulfillment="delivery").status_code, 400)
        self.assertEqual(self.submit(fulfillment="delivery", address="Calle 123").status_code, 400)
        response = self.submit(fulfillment="delivery", address="Calle 123", locality="Sourdeaux", reference="Piso 2")
        order = Order.objects.get(pk=response.json()["number"])
        self.assertEqual(order.address, "Calle 123")
        self.assertEqual(order.locality, "Sourdeaux")
        self.assertEqual(order.delivery_fee, 1500)
        self.assertEqual(order.total, order.products_total + 1500)

    def test_retries_do_not_duplicate_orders(self):
        first = self.submit().json()
        self.assertEqual(self.submit().json(), first)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Order.objects.get().items.count(), 1)

    def test_invalid_customer_data_and_other_session_are_rejected(self):
        for changes in ({"name": " "}, {"phone": "123"}, {"phone": "letters12345678"},
                        {"fulfillment": "invalid"}, {"name": "x" * 101}):
            with self.subTest(changes=changes):
                self.assertEqual(self.submit(**changes).status_code, 400)
        stranger = Client()
        self.assertEqual(stranger.post(reverse("checkout"), json.dumps(self.payload),
                                       content_type="application/json").status_code, 409)
        self.assertEqual(Order.objects.count(), 0)

    def test_price_and_availability_changes_prevent_submission(self):
        self.burger.price += 1
        self.burger.save()
        self.assertEqual(self.submit().status_code, 409)
        self.burger.available = False
        self.burger.save()
        self.assertEqual(self.submit().status_code, 409)
        self.assertEqual(Order.objects.count(), 0)

    def test_cart_changes_invalidate_previous_checkout(self):
        self.client.post(reverse("cart"), json.dumps({"action": "clear"}), content_type="application/json")
        self.assertEqual(self.submit().status_code, 409)
        self.assertEqual(Order.objects.count(), 0)

    def test_failure_rolls_back_order_and_keeps_cart(self):
        from unittest.mock import patch
        with patch("menu.views.OrderItem.objects.bulk_create", side_effect=RuntimeError("test")):
            with self.assertRaises(RuntimeError):
                self.submit()
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(self.client.get(reverse("cart")).json()["count"], 2)

    def test_endpoint_requires_post_and_csrf(self):
        self.assertEqual(self.client.get(reverse("checkout")).status_code, 405)
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse("checkout"), json.dumps(self.payload),
                                     content_type="application/json").status_code, 403)

    def test_admin_can_view_order_and_preserves_payment_snapshot(self):
        from django.contrib.auth import get_user_model
        from django.contrib import admin
        response = self.submit()
        order = Order.objects.get(pk=response.json()["number"])
        user = get_user_model().objects.create_superuser(username="testadmin", password="test-only")
        self.client.force_login(user)
        page = self.client.get(reverse("admin:menu_order_change", args=[order.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Cliente prueba")
        self.assertContains(page, "Sin sal")
        order_admin = admin.site._registry[Order]
        self.assertIn("payment_status", order_admin.readonly_fields)
        self.assertIn("products_total", order_admin.readonly_fields)


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class BurgerPhotoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model
        cls.admin_user = get_user_model().objects.create_superuser(username="photo-admin", password="test-only")

    def setUp(self):
        self.burger = Burger.objects.create(name="Foto prueba", description="Prueba", price=8000)
        self.client.force_login(self.admin_user)
        self.url = reverse("admin:menu_burger_change", args=[self.burger.pk])

    def photo(self, name="test.jpg", fmt="JPEG"):
        from io import BytesIO
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        data = BytesIO()
        Image.new("RGB", (80, 60), "orange").save(data, format=fmt)
        return SimpleUploadedFile(name, data.getvalue(), content_type="image/" + fmt.lower())

    def save_admin(self, **overrides):
        return self.client.post(self.url, {
            "name": "Foto prueba", "description": "Prueba", "price": 8000,
            "order": 0, "discount_percent": 0, "available": "on", "_save": "Guardar", **overrides,
        })

    def test_upload_through_admin_is_visible_and_survives_rename(self):
        self.assertEqual(self.save_admin(photo=self.photo()).status_code, 302)
        self.burger.refresh_from_db()
        path = self.burger.photo.name
        self.assertTrue(path.startswith("hamburguesas/"))
        self.assertTrue(self.burger.photo.storage.exists(path))
        self.assertContains(self.client.get(reverse("index")), self.burger.photo.url)
        self.burger.name = "Nuevo nombre"
        self.burger.save()
        self.burger.refresh_from_db()
        self.assertEqual(self.burger.photo.name, path)
        self.assertContains(self.client.get(self.url), "Vista previa")

    def test_replacement_has_new_url_and_clear_shows_placeholder(self):
        self.save_admin(photo=self.photo())
        self.burger.refresh_from_db()
        first = self.burger.photo.url
        self.save_admin(photo=self.photo())
        self.burger.refresh_from_db()
        self.assertNotEqual(self.burger.photo.url, first)
        current = self.burger.photo.url
        self.assertEqual(self.save_admin(**{"photo-clear": "on"}).status_code, 302)
        self.burger.refresh_from_db()
        self.assertFalse(self.burger.photo)


        page = self.client.get(reverse("index"))
        self.assertNotContains(page, current)
        self.assertContains(page, "Foto próximamente")

    def test_invalid_images_and_oversized_upload_do_not_replace_photo(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.save_admin(photo=self.photo())
        self.burger.refresh_from_db()
        original = self.burger.photo.name
        big = SimpleUploadedFile("large.jpg", self.photo().read() + b"\0" * (5 * 1024 * 1024),
                                 content_type="image/jpeg")
        for upload in (SimpleUploadedFile("fake.jpg", b"not an image"),
                       self.photo("test.gif", "GIF"), self.photo("wrong.png", "JPEG"), big):
            with self.subTest(filename=upload.name):
                response = self.save_admin(photo=upload)
                self.assertEqual(response.status_code, 200)
                self.assertIn("photo", response.context["adminform"].form.errors)
                self.burger.refresh_from_db()
                self.assertEqual(self.burger.photo.name, original)

    def test_png_and_webp_are_accepted(self):
        for fmt in ("PNG", "WEBP"):
            with self.subTest(fmt=fmt):
                self.assertEqual(self.save_admin(photo=self.photo("test." + fmt.lower(), fmt)).status_code, 302)

    def test_non_admin_cannot_upload(self):
        self.client.logout()
        self.assertEqual(self.save_admin(photo=self.photo()).status_code, 302)
        self.burger.refresh_from_db()
        self.assertFalse(self.burger.photo)



class SuggestionsTests(TestCase):
    def setUp(self):
        Product.objects.update(suggested=False)
        self.burger = Burger.objects.create(name="Hamburguesa prueba", description="Carne", price=8000)
        self.soda = Product.objects.create(name="Bebida prueba 600 ml", category="drink", price=2500,
                                           available=True, suggested=True, order=2)
        self.fries = Product.objects.create(name="Papas prueba", category="side", price=5000,
                                            available=True, suggested=True, order=1)
        self.cart_url = reverse("cart")

    def add(self, **kwargs):
        return self.client.post(self.cart_url, json.dumps({"action": "add", **kwargs}), content_type="application/json")

    def test_recommendations_follow_owner_order_and_exclude_cart_products(self):
        initial = self.client.get(self.cart_url).json()
        self.assertEqual([p["id"] for p in initial["suggestions"]], [self.fries.pk, self.soda.pk])
        cart = self.add(product_type="product", product_id=self.fries.pk, qty=1).json()
        self.assertEqual([p["id"] for p in cart["suggestions"]], [self.soda.pk])
        self.assertEqual(cart["total"], 5000)
        self.soda.suggested = False
        self.soda.save()
        self.assertEqual(self.client.get(self.cart_url).json()["suggestions"], [])

    def test_mixed_cart_prices_and_saved_order(self):
        self.add(burger_id=self.burger.pk, qty=1)
        cart = self.add(product_type="product", product_id=self.soda.pk, qty=2).json()
        self.assertEqual(cart["total"], 13000)
        result = self.client.post(reverse("checkout"), json.dumps({
            "name": "Cliente", "phone": "1155551234", "fulfillment": "pickup",
            "checkout_token": cart["checkout_token"], "products_total": cart["total"],
        }), content_type="application/json")
        self.assertEqual(result.status_code, 200)
        order = Order.objects.get(pk=result.json()["number"])
        self.assertEqual(order.items.count(), 2)
        item = order.items.get(product=self.soda)
        self.soda.price = 9999
        self.soda.save()
        self.soda.delete()
        item.refresh_from_db()
        self.assertEqual(item.unit_price, 2500)
        self.assertEqual(item.product_name, "Bebida prueba 600 ml")

    def test_quantities_remove_and_current_prices(self):
        item = self.add(product_type="product", product_id=self.soda.pk, qty=1, price=1).json()["items"][0]
        response = self.client.post(self.cart_url, json.dumps({"action": "quantity", "id": item["id"], "qty": 3}), content_type="application/json")
        self.assertEqual(response.json()["total"], 7500)
        self.soda.price = 3000
        self.soda.save()
        self.assertEqual(self.client.get(self.cart_url).json()["total"], 9000)
        self.client.post(self.cart_url, json.dumps({"action": "remove", "id": item["id"]}), content_type="application/json")
        self.assertEqual(self.client.get(self.cart_url).json()["count"], 0)

    def test_unavailable_products_are_neither_sold_nor_suggested(self):
        self.add(product_type="product", product_id=self.soda.pk, qty=1)
        self.soda.available = False
        self.soda.save()
        cart = self.client.get(self.cart_url).json()
        self.assertFalse(cart["can_continue"])
        self.assertNotIn(self.soda.pk, [p["id"] for p in cart["suggestions"]])
        self.assertEqual(self.add(product_type="product", product_id=self.soda.pk, qty=1).status_code, 400)

    def test_price_required_for_availability_and_extras_rejected(self):
        from django.core.exceptions import ValidationError
        product = Product(name="Sin precio", category="drink", available=True)
        with self.assertRaises(ValidationError):
            product.full_clean()
        product.available = False
        product.full_clean()
        self.assertEqual(self.add(product_type="product", product_id=self.soda.pk, qty=1, extras=[1]).status_code, 400)

    def test_products_can_be_bought_without_a_burger(self):
        page = self.client.get(reverse("index"))
        self.assertContains(page, "Bebida prueba 600 ml")
        cart = self.add(product_type="product", product_id=self.soda.pk, qty=1).json()
        self.assertTrue(cart["can_continue"])
