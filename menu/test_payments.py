from copy import deepcopy
from datetime import datetime, timezone as dt_timezone
import hashlib
import hmac
import json
import time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .mercadopago import PaymentError, start_payment, sync_payment
from .models import Order, OrderItem, PaymentAttempt


@override_settings(MP_ENABLED=True, MP_ENVIRONMENT="test", MP_ACCESS_TOKEN="fake-token",
                   MP_WEBHOOK_SECRET="fake-webhook-secret", MP_SELLER_ID="123", MP_APPLICATION_ID="456",
                   MP_PUBLIC_BASE_URL="https://arena.example")
class PaymentTests(TestCase):
    def setUp(self):
        self.order = Order.objects.create(customer_name="Prueba", phone="1155551234", fulfillment="delivery",
                                          products_total=8000, delivery_fee=1500, total=9500)
        OrderItem.objects.create(order=self.order, product_name="Hamburguesa prueba", quantity=1, unit_price=8000, subtotal=8000)
        session = self.client.session
        session["last_order_token"] = str(self.order.checkout_token)
        session.save()

    def resource(self, attempt, status="created", **overrides):
        return {"id": "ORDTST123", "external_reference": str(attempt.pk), "total_amount": "9500.00",
                "total_paid_amount": "9500.00" if status == "processed" else "0.00", "status": status,
                "status_detail": "accredited" if status == "processed" else status,
                "currency": "ARS", "user_id": "123", "integration_data": {"application_id": "456"},
                "checkout_url": "https://www.mercadopago.com.ar/checkout/v1/redirect?order_id=ORDTST123",
                "last_updated_date": "2026-11-14T12:00:00Z", **overrides}

    def attempt(self):
        return PaymentAttempt.objects.create(order=self.order, amount=9500, environment="test", provider_order_id="ORDTST123", status="pending")

    def notify(self, attempt, signature=None, live=False, action="order.processed"):
        ts = str(int(time.time() * 1000))
        manifest = f"id:{attempt.provider_order_id.lower()};request-id:test-request;ts:{ts};"
        sig = hmac.new(b"fake-webhook-secret", manifest.encode(), hashlib.sha256).hexdigest()
        return self.client.post(reverse("payment_webhook") + "?data.id=" + attempt.provider_order_id + "&type=order",
            json.dumps({"action": action, "type": "order", "live_mode": live, "data": {"id": attempt.provider_order_id}}),
            content_type="application/json", HTTP_X_REQUEST_ID="test-request", HTTP_X_SIGNATURE=signature or f"ts={ts},v1={sig}")

    def test_creates_checkout_from_server_snapshots_and_reuses_it(self):
        def create(method, path, payload=None, key=None):
            self.assertEqual(path, "/v1/orders")
            self.assertEqual(payload["total_amount"], "9500.00")
            self.assertEqual(payload["capture_mode"], "automatic_async")
            self.assertEqual(payload["items"][-1]["title"], "Envío")
            self.assertEqual(str(key), payload["external_reference"])
            return self.resource(PaymentAttempt.objects.get(pk=key))
        with patch("menu.mercadopago.api", side_effect=create) as api:
            first = start_payment(self.order)
            second = start_payment(self.order)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(api.call_count, 1)
        self.assertEqual(self.order.payment_attempts.count(), 1)

    @override_settings(MP_CAPTURE_MODE="automatic")
    def test_binary_rejection_can_retry_same_order_and_receive_approval(self):
        first = self.attempt()
        with patch("menu.mercadopago.api", return_value=self.resource(first, "failed")):
            sync_payment(first)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "failed")

        def create(method, path, payload=None, key=None):
            self.assertEqual(payload["capture_mode"], "automatic")
            return self.resource(PaymentAttempt.objects.get(pk=key), id="ORDTST456")

        with patch("menu.mercadopago.api", side_effect=create) as api:
            second = start_payment(self.order)
            self.assertEqual(start_payment(self.order).pk, second.pk)
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(api.call_count, 1)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(self.order.payment_attempts.count(), 2)
        with patch("menu.mercadopago.api", return_value=self.resource(second, "processed", id="ORDTST456")):
            sync_payment(second)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "paid")

    def test_action_required_offers_retry_without_creating_another_attempt(self):
        attempt = self.attempt()
        attempt.checkout_url = self.resource(attempt)["checkout_url"]
        attempt.save(update_fields=["checkout_url"])
        with patch("menu.mercadopago.api", return_value=self.resource(attempt, "action_required", status_detail="waiting_retry")):
            self.assertEqual(self.notify(attempt).status_code, 200)
        response = self.client.get(reverse("payment_return", args=[attempt.pk]))
        self.assertContains(response, "El pago necesita otra acción")
        self.assertContains(response, "Volver a intentar el pago")
        self.assertNotContains(response, "Estamos esperando la confirmación")
        with patch("menu.mercadopago.api") as api:
            self.assertEqual(start_payment(self.order).pk, attempt.pk)
        api.assert_not_called()
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "pending")
        self.assertEqual(self.order.payment_attempts.count(), 1)

    def test_timeout_preserves_idempotency_key(self):
        with patch("menu.mercadopago.api", side_effect=PaymentError("timeout")):
            with self.assertRaises(PaymentError):
                start_payment(self.order)
        saved = PaymentAttempt.objects.get(order=self.order)
        with patch("menu.mercadopago.api", return_value=self.resource(saved)) as api:
            recovered = start_payment(self.order)
        self.assertEqual(recovered.pk, saved.pk)
        self.assertEqual(api.call_args.kwargs["key"], saved.pk)

    def test_disabled_configuration_cannot_start_payments(self):
        with override_settings(MP_ENABLED=False), patch("menu.mercadopago.api") as api:
            with self.assertRaises(PaymentError):
                start_payment(self.order)
        api.assert_not_called()
        self.assertEqual(PaymentAttempt.objects.count(), 0)

    def test_invalid_provider_amount_or_account_never_marks_paid(self):
        attempt = self.attempt()
        for changes in ({"total_amount": "1"}, {"user_id": "999"}, {"currency": "USD"},
                        {"external_reference": "other"}, {"integration_data": {"application_id": "999"}}):
            with self.subTest(changes=changes), patch("menu.mercadopago.api", return_value=self.resource(attempt, "processed", **changes)):
                with self.assertRaises(PaymentError):
                    sync_payment(attempt)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "pending")

    def test_webhook_approval_is_idempotent(self):
        attempt = self.attempt()
        with patch("menu.mercadopago.api", return_value=self.resource(attempt, "processed")):
            self.assertEqual(self.notify(attempt).status_code, 200)
            self.assertEqual(self.notify(attempt).status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "paid")
        self.assertEqual(PaymentAttempt.objects.count(), 1)

    def test_webhook_invalid_signature_environment_and_transient_failure(self):
        attempt = self.attempt()
        with patch("menu.mercadopago.api") as api:
            self.assertEqual(self.notify(attempt, signature="ts=0,v1=bad").status_code, 401)
            self.assertEqual(self.notify(attempt, live=True).status_code, 400)
        api.assert_not_called()
        with patch("menu.mercadopago.api", side_effect=PaymentError("timeout")):
            self.assertEqual(self.notify(attempt).status_code, 503)

    def test_failed_attempt_event_does_not_override_processing_resource(self):
        attempt = self.attempt()
        with patch("menu.mercadopago.api", return_value=self.resource(attempt, "processing", status_detail="in_process")):
            response = self.notify(attempt, action="order.transaction_attempt_failed")
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(attempt.provider_status, "processing")
        self.assertEqual(self.order.payment_status, "pending")
        with patch("menu.mercadopago.api", return_value=self.resource(attempt, "failed", last_updated_date="2026-11-14T12:05:00Z")):
            response = self.notify(attempt, action="order.transaction_attempt_failed")
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "failed")

    def test_reconcile_command_recovers_missed_final_state_without_creating_payments(self):
        from io import StringIO
        from django.core.management import call_command
        attempt = self.attempt()
        output = StringIO()
        with patch("menu.mercadopago.api", return_value=self.resource(attempt, "failed")) as api:
            call_command("reconcile_payments", order=self.order.pk, stdout=output)
        self.assertEqual(api.call_args.args[0], "GET")
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "failed")
        self.assertEqual(PaymentAttempt.objects.count(), 1)
        self.assertIn("Rechazado", output.getvalue())

    def test_return_query_parameters_are_not_payment_confirmation(self):
        attempt = self.attempt()
        response = self.client.get(reverse("payment_return", args=[attempt.pk]), {"status": "approved", "collection_status": "approved"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "esperando la confirmación")
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "pending")

    def test_stale_results_do_not_overwrite_newer_payment_and_refunds_are_saved(self):
        attempt = self.attempt()
        with patch("menu.mercadopago.api", return_value=self.resource(attempt, "processed")):
            sync_payment(attempt)
        with patch("menu.mercadopago.api", return_value=self.resource(attempt, "failed", last_updated_date="2026-11-14T11:00:00Z")):
            sync_payment(attempt)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "paid")
        with patch("menu.mercadopago.api", return_value=self.resource(attempt, "refunded", last_updated_date="2026-11-14T13:00:00Z")):
            sync_payment(attempt)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "refunded")

    def test_late_failed_attempt_cannot_erase_successful_payment(self):
        first = self.attempt()
        second = PaymentAttempt.objects.create(order=self.order, amount=9500, environment="test", provider_order_id="ORDTST456", status="paid")
        with patch("menu.mercadopago.api", return_value=self.resource(first, "failed")):
            sync_payment(first)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, "paid")

    def test_payment_routes_are_private_and_csrf_protected(self):
        attempt = self.attempt()
        url = reverse("payment_start", args=[self.order.checkout_token])
        self.assertEqual(Client().post(url).status_code, 403)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(Client(enforce_csrf_checks=True).post(url).status_code, 403)
        self.assertEqual(Client().get(reverse("payment_return", args=[attempt.pk])).status_code, 403)

    def test_pending_payment_cannot_start_preparation_when_payments_enabled(self):
        user = get_user_model().objects.create_superuser(username="payment-admin", password="test-only")
        self.client.force_login(user)
        response = self.client.post(reverse("owner_order_status", args=[self.order.pk]), {"status": "preparing", "expected_status": "new"})
        self.assertEqual(response.status_code, 400)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "new")

    def test_local_panel_protects_orders_started_in_the_public_test_instance(self):
        self.attempt()
        user = get_user_model().objects.create_superuser(username="local-payment-admin", password="test-only")
        self.client.force_login(user)
        with override_settings(MP_ENABLED=False):
            response = self.client.post(reverse("owner_order_status", args=[self.order.pk]),
                                        {"status": "preparing", "expected_status": "new"})
        self.assertEqual(response.status_code, 400)
