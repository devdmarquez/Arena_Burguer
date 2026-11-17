from django.test import Client, TestCase, override_settings
from django.urls import resolve, Resolver404


@override_settings(ROOT_URLCONF='config.payment_test_urls', DEBUG=False)
class PublicTunnelTests(TestCase):
    def test_private_routes_and_files_are_not_exposed(self):
        for url in ('/admin/', '/admin/login/', '/gestion/', '/gestion/pedidos/', '/gestion/ingresar/',
                    '/gestion/estadisticas/', '/.env', '/.local/', '/config/settings.py'):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 404)
                self.assertNotContains(response, 'Traceback', status_code=404)

    def test_shop_and_assets_still_work(self):
        self.assertContains(self.client.get('/'), 'Arena Burger')
        self.assertEqual(self.client.get('/carrito/').status_code, 200)
        response = self.client.get('/static/menu/logo.jpeg')
        self.assertEqual(response.status_code, 200)
        response.close()
        self.assertEqual(self.client.get('/media/').status_code, 404)

    def test_webhook_is_registered_but_payments_stay_disabled(self):
        with override_settings(MP_ENABLED=False):
            self.assertEqual(self.client.post('/pagos/notificaciones/').status_code, 503)
