# Desactivado para la primera version. Codigo conservado para reactivarlo despues.
# from datetime import datetime
# from decimal import Decimal
# from zoneinfo import ZoneInfo
#
# from django.contrib.auth import get_user_model
# from django.contrib.auth.models import Permission
# from django.test import TestCase
# from django.urls import reverse
#
# from .models import Burger, Order, OrderItem, Product
#
#
# class StatisticsTests(TestCase):
#     @classmethod
#     def setUpTestData(cls):
#         cls.owner = get_user_model().objects.create_user(username="reports-owner")
#         cls.owner.user_permissions.add(Permission.objects.get(content_type__app_label="menu", codename="view_order"))
#         cls.burger = Burger.objects.create(name="Clásica reporte", description="Carne", price=8000)
#         cls.drink = Product.objects.create(name="Bebida reporte", category="drink", price=2500, available=True)
#
#     def setUp(self):
#         self.url = reverse("owner_statistics")
#         self.filters = {"start": "2026-10-01", "end": "2026-10-31"}
#         self.client.force_login(self.owner)
#
#     def order(self, payment="paid", status="completed", day=10):
#         order = Order.objects.create(customer_name="Reporte prueba", phone="1155551234", fulfillment="delivery",
#                                       products_total=19500, delivery_fee=2000, total=21500,
#                                       payment_status=payment, status=status)
#         Order.objects.filter(pk=order.pk).update(created_at=datetime(2026, 10, day, 20, tzinfo=ZoneInfo("America/Argentina/Buenos_Aires")))
#         OrderItem.objects.create(order=order, burger=self.burger, product_name="Clásica histórica", quantity=2,
#                                   unit_price=8500, subtotal=17000, extras=[{"name": "Cheddar", "price": 500}])
#         OrderItem.objects.create(order=order, product=self.drink, product_name="Bebida histórica", quantity=1,
#                                   unit_price=2500, subtotal=2500)
#         return order
#
#     def test_paid_sales_use_snapshots_exclude_shipping_pending_and_cancelled(self):
#         self.order()
#         self.order(payment="pending")
#         self.order(payment="paid", status="cancelled")
#         self.order(payment="failed")
#         self.burger.price = 99999
#         self.burger.save()
#         response = self.client.get(self.url, self.filters)
#         self.assertEqual(response.status_code, 200)
#         self.assertEqual(response.context["sales"], 1)
#         self.assertEqual(response.context["revenue"], 19500)
#         self.assertEqual(response.context["units"], 3)
#         self.assertEqual(response.context["average"], Decimal(19500))
#         self.assertEqual(response.context["pending"], 1)
#         self.assertEqual(response.context["cancelled"], 1)
#         self.assertContains(response, "no son ganancia neta")
#         self.assertIn("no-store", response.headers["Cache-Control"])
#
#     def test_burger_filter_counts_only_selected_lines_and_orders_once(self):
#         order = self.order()
#         OrderItem.objects.create(order=order, burger=self.burger, product_name="Clásica histórica", quantity=1,
#                                   unit_price=8000, subtotal=8000)
#         response = self.client.get(self.url, self.filters | {"burger": self.burger.pk})
#         self.assertEqual(response.context["sales"], 1)
#         self.assertEqual(response.context["revenue"], 25000)
#         self.assertEqual(response.context["units"], 3)
#         self.assertEqual(len(response.context["ranking"]), 1)
#
#     def test_local_date_boundaries(self):
#         inside = self.order(day=31)
#         outside = self.order()
#         tz = ZoneInfo("America/Argentina/Buenos_Aires")
#         Order.objects.filter(pk=inside.pk).update(created_at=datetime(2026, 10, 31, 23, 59, tzinfo=tz))
#         Order.objects.filter(pk=outside.pk).update(created_at=datetime(2026, 11, 1, 0, 0, tzinfo=tz))
#         result = self.client.get(self.url, self.filters)
#         self.assertEqual(result.context["sales"], 1)
#         self.assertEqual(result.context["timeline"][-1]["revenue"], 19500)
#
#     def test_invalid_ranges_and_empty_results(self):
#         for filters in ({"start": "bad", "end": "2026-10-31"},
#                         {"start": "2026-10-31", "end": "2026-10-01"},
#                         {"start": "2024-01-01", "end": "2026-10-31"},
#                         self.filters | {"burger": "999999999"}):
#             self.assertEqual(self.client.get(self.url, filters).status_code, 400)
#         response = self.client.get(self.url, self.filters)
#         self.assertEqual(response.context["sales"], 0)
#         self.assertEqual(response.context["average"], 0)
#         self.assertContains(response, "Todavía no hay ventas pagadas")
#
#     def test_default_period_and_monthly_chart(self):
#         from django.utils import timezone
#         response = self.client.get(self.url)
#         self.assertEqual(response.context["start"], timezone.localdate().replace(day=1))
#         response = self.client.get(self.url, {"start": "2026-01-01", "end": "2026-10-31"})
#         self.assertTrue(response.context["monthly"])
#         self.assertEqual(len(response.context["timeline"]), 10)
#
#     def test_private_access(self):
#         self.client.logout()
#         self.assertEqual(self.client.get(self.url).status_code, 302)
#         stranger = get_user_model().objects.create_user(username="reports-stranger", is_staff=True)
#         self.client.force_login(stranger)
#         self.assertEqual(self.client.get(self.url).status_code, 403)
