import json
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, Client, override_settings
from django.urls import reverse

from .models import Burger, Order
from .shipping import ShippingError, calculate, fee_for_distance, make_quote, verify_quote


class ShippingMathTests(SimpleTestCase):
    def test_bands_and_radius(self):
        for distance, expected in [(0, 1000), (.001, 1500), (499, 1500), (500, 1500),
                                   (500.001, 2000), (1000, 2000), (2999, 4000), (3000, 4000)]:
            self.assertEqual(fee_for_distance(distance), expected)
        for distance in (3000.001, -1, float("nan"), float("inf")):
            with self.assertRaises(ShippingError):
                fee_for_distance(distance)

    def test_straight_line_distance_and_coordinates(self):
        distance, fee = calculate(-34.4972319, -58.6706307)
        self.assertAlmostEqual(distance, 111.2, delta=.2)
        self.assertEqual(fee, 1500)
        for point in ((91, 0), (0, 181), (float("nan"), 0), (-34.4, -58.67)):
            with self.assertRaises(ShippingError):
                calculate(*point)

    def test_quote_tampering_expiry_and_address_changes(self):
        quote = make_quote("Calle 123", "-34.4972319", "-58.6706307")["shipping_quote"]
        self.assertEqual(verify_quote(quote, "Calle 123")[2], 1500)
        for token, address in ((quote + "bad", "Calle 123"), (quote, "Otra calle 123")):
            with self.assertRaises(ShippingError):
                verify_quote(token, address)
        import time
        with patch("django.core.signing.time.time", return_value=time.time() + 1000):
            with self.assertRaises(ShippingError):
                verify_quote(quote, "Calle 123")
        with override_settings(STORE_LATITUDE="-34.4980"):
            with self.assertRaises(ShippingError):
                verify_quote(quote, "Calle 123")


class ShippingCheckoutTests(TestCase):
    def setUp(self):
        burger = Burger.objects.create(name="Envio prueba", description="Carne", price=8000)
        cart = self.client.post(reverse("cart"), json.dumps({"action": "add", "burger_id": burger.pk, "qty": 1}), content_type="application/json").json()
        self.order_data = {"name": "Cliente", "phone": "1155551234", "fulfillment": "delivery",
                           "address": "Calle 123", "locality": "Sourdeaux", "products_total": 8000, "checkout_token": cart["checkout_token"]}

    def test_fixed_fee_is_authoritative_and_location_is_not_required(self):
        response = self.client.post(reverse("checkout"), json.dumps({**self.order_data,
            "delivery_fee": 1, "total": 1, "shipping_quote": "obsolete", "latitude": 0, "longitude": 0}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        order = Order.objects.get(pk=response.json()["number"])
        self.assertEqual(order.delivery_fee, 1500)
        self.assertEqual(order.total, 9500)
        self.assertEqual(order.locality, "Sourdeaux")
        self.assertIsNone(order.delivery_latitude)
        self.assertIsNone(order.delivery_distance_m)

    def test_missing_locality_cannot_create_delivery_order(self):
        response = self.client.post(reverse("checkout"), json.dumps({**self.order_data, "locality": " "}), content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Order.objects.exists())

    def test_map_and_quote_route_are_paused(self):
        response = self.client.get(reverse("index"))
        self.assertNotContains(response, "leaflet")
        self.assertNotContains(response, 'id="shipping-url"')
        self.assertEqual(self.client.post('/envio/cotizar/', '{}', content_type='application/json').status_code, 404)

    def test_pickup_remains_free_and_clears_delivery_fields(self):
        response = self.client.post(reverse("checkout"), json.dumps({**self.order_data, "fulfillment": "pickup"}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        order = Order.objects.get(pk=response.json()["number"])
        self.assertEqual(order.delivery_fee, 0)
        self.assertEqual(order.total, 8000)
        self.assertEqual(order.address, '')
        self.assertEqual(order.locality, '')
