"""Lista explícita de rutas públicas. No registra /admin/ ni /gestion/."""
from django.conf import settings
from django.contrib.staticfiles.views import serve as serve_static
from django.urls import path
from django.views.static import serve as serve_media

from menu import views, payment_views


def menu_static(request, path):
    return serve_static(request, 'menu/' + path, insecure=True)


urlpatterns = [
    path('', views.index, name='index'),
    path('nosotros/', views.about, name='about'),
    path('carrito/', views.cart, name='cart'),
    path('pedido/', views.checkout, name='checkout'),
    path('pagos/<uuid:token>/iniciar/', payment_views.start, name='payment_start'),
    path('pagos/retorno/<uuid:attempt_id>/', payment_views.returned, name='payment_return'),
    path('pagos/estado/<uuid:attempt_id>/', payment_views.refresh, name='payment_refresh'),
    path('pagos/notificaciones/', payment_views.webhook, name='payment_webhook'),
    path('static/menu/<path:path>', menu_static),
    path('media/<path:path>', serve_media, {'document_root': settings.MEDIA_ROOT, 'show_indexes': False}),
]
