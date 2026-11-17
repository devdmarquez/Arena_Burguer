from django.contrib import admin
from django.utils.html import format_html

from .models import Aderezo, Burger, Extra, Product, Order, OrderItem, PaymentAttempt, AboutPhoto


@admin.register(AboutPhoto)
class AboutPhotoAdmin(admin.ModelAdmin):
    list_display = ("title", "active", "order")
    list_editable = ("active", "order")
    list_filter = ("active",)


class PricingAdmin(admin.ModelAdmin):
    @admin.display(description="Precio final")
    def final_price(self, obj):
        return obj.sale_price


@admin.register(Burger)
class BurgerAdmin(PricingAdmin):
    list_display = ("name", "photo_preview", "price", "discount_active", "discount_percent", "final_price", "available", "order")
    list_editable = ("price", "discount_active", "discount_percent", "available", "order")
    readonly_fields = ("photo_preview",)

    @admin.display(description="Vista previa")
    def photo_preview(self, obj):
        if not obj or not obj.photo:
            return "Sin foto"
        return format_html('<img src="{}" alt="{}" style="width:120px;height:90px;object-fit:cover;border-radius:8px">',
                           obj.photo.url, obj.name)


@admin.register(Aderezo)
class AderezoAdmin(admin.ModelAdmin):
    list_display = ("name", "available")
    list_editable = ("available",)


@admin.register(Product)
class ProductAdmin(PricingAdmin):
    list_display = ("name", "category", "price", "discount_active", "discount_percent", "final_price", "available", "suggested", "order")
    list_editable = ("price", "discount_active", "discount_percent", "available", "suggested", "order")
    list_filter = ("category", "available", "suggested")
    search_fields = ("name",)


@admin.register(Extra)
class ExtraAdmin(PricingAdmin):
    list_display = ("name", "price", "discount_active", "discount_percent", "final_price", "available")
    list_editable = ("price", "discount_active", "discount_percent", "available")


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = ("product_name", "quantity", "unit_price", "subtotal", "aderezos", "extras", "notes")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "customer_name", "fulfillment", "products_total", "total", "payment_status", "status")
    list_filter = ("fulfillment", "payment_status", "status", "created_at")
    search_fields = ("=id", "customer_name", "phone")
    readonly_fields = tuple(field.name for field in Order._meta.fields if field.name != "status")
    inlines = [OrderItemInline]

    def has_add_permission(self, request):
        return False


@admin.register(PaymentAttempt)
class PaymentAttemptAdmin(admin.ModelAdmin):
    list_display = ("order", "amount", "environment", "status", "created_at")
    list_filter = ("environment", "status")
    readonly_fields = tuple(field.name for field in PaymentAttempt._meta.fields)
    exclude = ("checkout_url",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
