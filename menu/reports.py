# Desactivado para la primera version. Codigo conservado para reactivarlo despues.
# from datetime import datetime, time, timedelta
# from decimal import Decimal
#
# from django import forms
# from django.contrib.auth.decorators import login_required, permission_required
# from django.db.models import Count, Sum
# from django.db.models.functions import TruncDate, TruncMonth
# from django.shortcuts import render
# from django.utils import timezone
# from django.views.decorators.cache import never_cache
#
# from .models import Burger, Order, OrderItem
#
#
# class ReportFilters(forms.Form):
#     start = forms.DateField(label="Desde", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
#     end = forms.DateField(label="Hasta", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
#     burger = forms.ModelChoiceField(label="Hamburguesa", queryset=Burger.objects.all(), required=False,
#                                     empty_label="Todos los productos")
#
#     def clean(self):
#         values = super().clean()
#         start, end = values.get("start"), values.get("end")
#         if start and end:
#             if end < start:
#                 raise forms.ValidationError("La fecha final debe ser igual o posterior a la inicial.")
#             elif (end - start).days > 365:
#                 raise forms.ValidationError("Elegí un período de hasta 366 días.")
#         return values
#
#
# @never_cache
# @login_required(login_url="owner_login")
# @permission_required("menu.view_order", raise_exception=True)
# def statistics(request):
#     today = timezone.localdate()
#     form = ReportFilters(request.GET if request.GET else {
#         "start": today.replace(day=1).isoformat(), "end": today.isoformat(),
#     })
#     context = {"form": form}
#     if not form.is_valid():
#         return render(request, "menu/panel/statistics.html", context, status=400)
#     start, end, burger = (form.cleaned_data[key] for key in ("start", "end", "burger"))
#     tz = timezone.get_current_timezone()
#     # Límites locales [inicio, fin): incluye todo el último día sin depender del reloj del servidor.
#     first = timezone.make_aware(datetime.combine(start, time.min), tz)
#     last = timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min), tz)
#     period_orders = Order.objects.filter(created_at__gte=first, created_at__lt=last)
#     if burger:
#         period_orders = period_orders.filter(items__burger=burger).distinct()
#     paid_orders = period_orders.filter(payment_status="paid").exclude(status="cancelled")
#     items = OrderItem.objects.filter(order__in=paid_orders)
#     if burger:
#         items = items.filter(burger=burger)
#     totals = items.aggregate(revenue=Sum("subtotal", default=0), units=Sum("quantity", default=0))
#     sales = paid_orders.count()
#     ranking = list(items.values("product_name").annotate(units=Sum("quantity"), revenue=Sum("subtotal"))
#                    .order_by("-units", "product_name"))
#     max_units = max((row["units"] for row in ranking), default=1)
#     for row in ranking:
#         row["width"] = max(1, round(row["units"] / max_units * 100))
#     monthly = (end - start).days > 62
#     truncate = TruncMonth("order__created_at", tzinfo=tz) if monthly else TruncDate("order__created_at", tzinfo=tz)
#     daily = list(items.annotate(period=truncate).values("period").annotate(revenue=Sum("subtotal")).order_by("period"))
#     amounts = {(row["period"].date() if monthly else row["period"]): row["revenue"] for row in daily}
#     timeline = []
#     cursor = start.replace(day=1) if monthly else start
#     while cursor <= end:
#         timeline.append({"date": cursor, "revenue": amounts.get(cursor, 0)})
#         if monthly:
#             cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
#         else:
#             cursor += timedelta(days=1)
#     peak = max((row["revenue"] for row in timeline), default=0) or 1
#     for row in timeline:
#         row["width"] = round(row["revenue"] / peak * 100)
#     context.update({
#         "has_report": True, "start": start, "end": end, "burger": burger,
#         "sales": sales, "revenue": totals["revenue"], "units": totals["units"],
#         "average": Decimal(totals["revenue"]) / sales if sales else Decimal(0),
#         "pending": period_orders.filter(payment_status="pending").exclude(status="cancelled").count(),
#         "cancelled": period_orders.filter(status="cancelled").count(),
#         "ranking": ranking, "timeline": timeline, "monthly": monthly,
#     })
#     return render(request, "menu/panel/statistics.html", context)
