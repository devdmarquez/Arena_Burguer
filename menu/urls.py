from django.urls import path

from . import views
from . import panel
from . import payment_views
# Estadísticas reservadas para una versión posterior.
# from . import reports
from django.contrib.auth.views import LogoutView
from django.views.generic.base import RedirectView

urlpatterns = [
    path("", views.index, name="index"),
    path("nosotros/", views.about, name="about"),
    path("carrito/", views.cart, name="cart"),
    path("pedido/", views.checkout, name="checkout"),
    path("pagos/<uuid:token>/iniciar/", payment_views.start, name="payment_start"),
    path("pagos/retorno/<uuid:attempt_id>/", payment_views.returned, name="payment_return"),
    path("pagos/estado/<uuid:attempt_id>/", payment_views.refresh, name="payment_refresh"),
    path("pagos/notificaciones/", payment_views.webhook, name="payment_webhook"),
    path("gestion/", RedirectView.as_view(pattern_name="owner_orders"), name="owner_home"),
    path("gestion/ingresar/", panel.OwnerLoginView.as_view(), name="owner_login"),
    path("gestion/salir/", LogoutView.as_view(next_page="owner_login"), name="owner_logout"),
    path("gestion/pedidos/", panel.orders, name="owner_orders"),
    # path("gestion/estadisticas/", reports.statistics, name="owner_statistics"),
    path("gestion/pedidos/<int:pk>/estado/", panel.update_status, name="owner_order_status"),
]
