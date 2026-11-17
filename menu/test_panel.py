from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from .models import Order, OrderItem


class OwnerPanelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(username="owner-test", password="test-password")
        cls.owner.user_permissions.add(*Permission.objects.filter(content_type__app_label="menu", codename__in=["view_order", "change_order"]))
        cls.stranger = User.objects.create_user(username="customer-test", password="test-password", is_staff=True)

    def setUp(self):
        self.order = Order.objects.create(customer_name="Cliente panel", phone="1155551234", fulfillment="pickup",
                                          products_total=9000, delivery_fee=0, total=9000)
        OrderItem.objects.create(order=self.order, product_name="Clásica", quantity=1, unit_price=9000,
                                 subtotal=9000, aderezos=["Mayonesa"], extras=[{"name": "Cheddar", "price": 500}], notes="Sin cebolla")
        self.url = reverse("owner_orders")
        self.change_url = reverse("owner_order_status", args=[self.order.pk])

    def test_private_access_and_staff_without_permission_is_denied(self):
        self.assertRedirects(self.client.get(self.url), reverse("owner_login") + "?next=" + self.url)
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.change_url, {"status": "preparing", "expected_status": "new"}).status_code, 403)

    def test_login_permissions_logout_and_safe_redirect(self):
        login = reverse("owner_login")
        self.assertContains(self.client.get(login), "Ingresar al panel")
        response = self.client.post(login, {"username": "customer-test", "password": "test-password"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertRedirects(self.client.post(login, {"username": "owner-test", "password": "test-password",
                                                     "next": "https://example.com"}), self.url)
        self.assertEqual(self.client.get(reverse("owner_logout")).status_code, 405)
        self.assertRedirects(self.client.post(reverse("owner_logout")), login)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_order_details_payment_and_filters(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        for text in ("Cliente panel", "Sin cebolla", "Cheddar", "Pendiente de pago", "Preparar pedido"):
            self.assertContains(response, text)
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertContains(self.client.get(self.url, {"status": "ready"}), "No hay pedidos")
        self.assertContains(self.client.get(self.url, {"q": str(self.order.pk)}), "Cliente panel")
        self.assertContains(self.client.get(self.url, {"q": "sin coincidencia"}), "No hay pedidos")
        self.assertContains(self.client.get(self.url, {"fulfillment": "delivery"}), "No hay pedidos")
        self.assertEqual(self.client.get(self.url, {"status": "invalid"}).status_code, 400)

    def test_state_sequence_does_not_mark_payment_as_paid(self):
        self.client.force_login(self.owner)
        for previous, following in (("new", "preparing"), ("preparing", "ready"), ("ready", "completed")):
            self.assertRedirects(self.client.post(self.change_url, {"status": following, "expected_status": previous}), self.url)
            self.order.refresh_from_db()
            self.assertEqual(self.order.status, following)
            self.assertEqual(self.order.payment_status, "pending")
        self.assertEqual(self.client.post(self.change_url, {"status": "new", "expected_status": "completed"}).status_code, 400)

    def test_stale_submission_cannot_overwrite_current_state(self):
        self.client.force_login(self.owner)
        self.client.post(self.change_url, {"status": "preparing", "expected_status": "new"})
        self.client.post(self.change_url, {"status": "cancelled", "expected_status": "new"})
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "preparing")

    def test_mutations_require_post_and_csrf(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(self.change_url).status_code, 405)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.post(self.change_url, {"status": "preparing", "expected_status": "new"}).status_code, 403)

    def test_readonly_user_and_escaping(self):
        User = get_user_model()
        reader = User.objects.create_user(username="reader-test")
        reader.user_permissions.add(Permission.objects.get(content_type__app_label="menu", codename="view_order"))
        self.order.customer_name = '<script>alert("test")</script>'
        self.order.save()
        self.client.force_login(reader)
        response = self.client.get(self.url)
        self.assertNotContains(response, "Preparar pedido")
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, '<script>alert("test")</script>')
        self.assertEqual(self.client.post(self.change_url, {"status": "preparing", "expected_status": "new"}).status_code, 403)

    def test_owner_setup_grants_catalogue_without_superuser(self):
        call_command("create_owner", self.stranger.username, stdout=StringIO())
        user = get_user_model().objects.get(pk=self.stranger.pk)
        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.has_perm("menu.change_order"))
        self.assertTrue(user.has_perm("menu.change_burger"))
        self.assertFalse(user.has_perm("auth.change_user"))
        self.assertFalse(user.has_perm("menu.delete_order"))

    def test_filters_are_preserved_without_external_redirects(self):
        self.client.force_login(self.owner)
        target = self.url + "?status=new&q=Cliente"
        response = self.client.post(self.change_url, {"status": "preparing", "expected_status": "new", "return_to": target})
        self.assertEqual(response.headers["Location"], target)
        response = self.client.post(self.change_url, {"status": "ready", "expected_status": "preparing", "return_to": "https://example.com/gestion/pedidos/"})
        self.assertEqual(response.headers["Location"], self.url)

    def test_cancellation_and_pagination(self):
        self.client.force_login(self.owner)
        response = self.client.post(self.change_url, {"status": "cancelled", "expected_status": "new"})
        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "cancelled")
        self.assertEqual(self.order.payment_status, "pending")
        Order.objects.bulk_create([Order(customer_name="Página", phone="1155551234", fulfillment="pickup",
                                         products_total=8000, total=8000, delivery_fee=0) for _ in range(36)])
        response = self.client.get(self.url)
        self.assertEqual(len(response.context["page_obj"]), 36)
        self.assertTrue(response.context["page_obj"].has_next())

    def test_create_owner_prompts_privately_and_grants_access(self):
        from unittest.mock import patch
        with patch("menu.management.commands.create_owner.getpass", return_value="Long-private-723-password"):
            call_command("create_owner", "new-owner-test", stdout=StringIO())
        user = get_user_model().objects.get(username="new-owner-test")
        self.assertTrue(user.check_password("Long-private-723-password"))
        self.assertFalse(user.is_superuser)
        self.client.force_login(user)
        self.assertEqual(self.client.get(self.url).status_code, 200)
