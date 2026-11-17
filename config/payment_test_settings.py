"""Instancia temporal para probar pagos por túnel; no es el servidor local habitual."""
import json

from .settings import *  # noqa: F403

runtime_file = BASE_DIR / '.local' / 'payment-tunnel.json'
if not runtime_file.is_file():
    raise ImproperlyConfigured('Primero configurá el túnel de prueba.')
runtime = json.loads(runtime_file.read_text(encoding='utf-8'))
from urllib.parse import urlsplit
public_url = runtime.get('public_url', '')
public_host = urlsplit(public_url).hostname
if not public_url.startswith('https://') or not public_host or not public_host.endswith('.trycloudflare.com'):
    raise ImproperlyConfigured('La URL del túnel no es válida.')

DEBUG = False
ROOT_URLCONF = 'config.payment_test_urls'
ALLOWED_HOSTS = ['localhost', '127.0.0.1', public_host]
CSRF_TRUSTED_ORIGINS = [public_url]
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
MP_PUBLIC_BASE_URL = public_url
if MP_ENVIRONMENT != 'test':
    raise ImproperlyConfigured('El túnel temporal solo permite el entorno de prueba.')
MP_ENABLED = runtime.get('payments_enabled') is True
# Resultado binario solo en esta instancia de prueba; requiere una order nueva.
MP_CAPTURE_MODE = 'automatic'
