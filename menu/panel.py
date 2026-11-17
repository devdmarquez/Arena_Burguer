from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from urllib.parse import urlsplit
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .models import Order


class OwnerAuthenticationForm(AuthenticationForm):
    username = forms.CharField(label="Usuario", widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"}))

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.has_perm("menu.view_order"):
            raise forms.ValidationError("Esta cuenta no tiene acceso al panel de pedidos.", code="no_access")


class OwnerLoginView(LoginView):
    template_name = "menu/panel/login.html"
    authentication_form = OwnerAuthenticationForm
    redirect_authenticated_user = True
    next_page = reverse_lazy("owner_orders")


TRANSITIONS = {
    Order.Status.NEW: [(Order.Status.PREPARING, "Preparar pedido"), (Order.Status.CANCELLED, "Cancelar pedido")],
    Order.Status.PREPARING: [(Order.Status.READY, "Marcar listo"), (Order.Status.CANCELLED, "Cancelar pedido")],
    Order.Status.READY: [(Order.Status.COMPLETED, "Marcar entregado"), (Order.Status.CANCELLED, "Cancelar pedido")],
    Order.Status.COMPLETED: [],
    Order.Status.CANCELLED: [],
}


@never_cache
@login_required(login_url="owner_login")
@permission_required("menu.view_order", raise_exception=True)
def orders(request):
    status = request.GET.get("status", "")
    valid_statuses = dict(Order.Status.choices)
    if status and status not in valid_statuses:
        return HttpResponseBadRequest("Estado no válido.")
    query = request.GET.get("q", "").strip()[:100]
    fulfillment = request.GET.get("fulfillment", "")
    if fulfillment and fulfillment not in dict(Order.Fulfillment.choices):
        return HttpResponseBadRequest("Modalidad no válida.")
    orders_qs = Order.objects.prefetch_related("items", "payment_attempts").order_by("-created_at", "-pk")
    if fulfillment:
        orders_qs = orders_qs.filter(fulfillment=fulfillment)
    if query:
        search = Q(customer_name__icontains=query) | Q(phone__icontains=query)
        if query.isascii() and query.isdigit() and len(query) < 19:
            search |= Q(pk=int(query))
        orders_qs = orders_qs.filter(search)
    counts = dict(orders_qs.values("status").annotate(count=Count("id")).values_list("status", "count"))
    all_count = sum(counts.values())
    if status:
        orders_qs = orders_qs.filter(status=status)
    page = Paginator(orders_qs, 36).get_page(request.GET.get("page"))
    can_change = request.user.has_perm("menu.change_order")
    for order in page:
        latest_attempt = next(iter(order.payment_attempts.all()), None)
        order.payment_label = order.get_payment_status_display()
        if (order.payment_status == "pending" and latest_attempt
                and latest_attempt.status == "pending" and latest_attempt.provider_status == "action_required"):
            order.payment_label = "Requiere reintento"
        order.transitions = TRANSITIONS[order.status] if can_change else []
        if (settings.MP_ENABLED or order.payment_attempts.exists()) and order.payment_status != "paid":
            order.transitions = [(value, label) for value, label in order.transitions if value == "cancelled"]
    tabs = [{"value": "", "label": "Todos", "count": all_count}] + [
        {"value": value, "label": label, "count": counts.get(value, 0)}
        for value, label in Order.Status.choices
    ]
    return render(request, "menu/panel/orders.html", {
        "page_obj": page, "tabs": tabs, "selected_status": status,
        "query": query, "fulfillment": fulfillment,
    })


@never_cache
@require_POST
@login_required(login_url="owner_login")
@permission_required(("menu.view_order", "menu.change_order"), raise_exception=True)
def update_status(request, pk):
    target = request.POST.get("status")
    expected = request.POST.get("expected_status")
    with transaction.atomic():
        order = get_object_or_404(Order.objects.select_for_update(), pk=pk)
        if (settings.MP_ENABLED or order.payment_attempts.exists()) and order.payment_status != "paid" and target != "cancelled":
            return HttpResponseBadRequest("El pago debe estar confirmado antes de preparar el pedido.")
        if expected != order.status:
            messages.warning(request, f"El pedido #{order.pk} cambió desde que abriste la pantalla. Revisá su estado actual.")
        elif target not in [value for value, label in TRANSITIONS[order.status]]:
            return HttpResponseBadRequest("El cambio de estado no está permitido.")
        else:
            order.status = target
            order.save(update_fields=["status"])
            messages.success(request, f"Pedido #{order.pk}: {order.get_status_display()}.")
    return_to = request.POST.get("return_to", "")
    try:
        parsed = urlsplit(return_to)
    except ValueError:
        return redirect("owner_orders")
    if not parsed.scheme and not parsed.netloc and parsed.path == reverse("owner_orders"):
        return redirect(return_to)
    return redirect("owner_orders")
