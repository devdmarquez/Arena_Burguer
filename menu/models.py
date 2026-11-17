from django.db import models
import uuid
from .images import burger_photo_path, product_photo_path, about_photo_path, validate_burger_photo
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator


class DiscountedPrice(models.Model):
    discount_active = models.BooleanField("descuento activo", default=False)
    discount_percent = models.PositiveSmallIntegerField("descuento (%)", default=0,
        validators=[MaxValueValidator(99)], help_text="De 1 a 99 cuando el descuento está activo. No incluye envío ni otros extras.")

    class Meta:
        abstract = True
        constraints = [
            models.CheckConstraint(condition=models.Q(discount_percent__lte=99), name="%(class)s_discount_range"),
            models.CheckConstraint(condition=models.Q(discount_active=False) | models.Q(discount_percent__gte=1, price__isnull=False, price__gte=1), name="%(class)s_active_discount_valid"),
        ]

    def clean(self):
        super().clean()
        if self.discount_active and (not isinstance(self.discount_percent, int) or not 1 <= self.discount_percent <= 99 or not self.price):
            raise ValidationError({"discount_percent": "Para activar la oferta, definí un precio mayor que cero y un descuento de 1 a 99%."})

    @property
    def has_discount(self):
        return bool(self.discount_active and self.price and 1 <= self.discount_percent <= 99)

    @property
    def sale_price(self):
        # Pesos enteros, redondeando al peso más cercano (medio peso hacia arriba).
        return max(1, (self.price * (100 - self.discount_percent) + 50) // 100) if self.has_discount else self.price


class Burger(DiscountedPrice):
    name = models.CharField("nombre", max_length=80)
    description = models.TextField("descripción")
    photo = models.ImageField("foto", upload_to=burger_photo_path, blank=True,
                              validators=[validate_burger_photo],
                              help_text="JPG, PNG o WebP. Máximo 5 MB y 16 megapíxeles. Podés reemplazarla o quitarla.")
    price = models.PositiveIntegerField("precio")
    available = models.BooleanField("disponible", default=True)
    order = models.PositiveIntegerField("orden", default=0)

    class Meta:
        constraints = DiscountedPrice.Meta.constraints
        ordering = ["order", "id"]
        verbose_name = "hamburguesa"
        verbose_name_plural = "hamburguesas"

    def __str__(self):
        return self.name


class Aderezo(models.Model):
    name = models.CharField("nombre", max_length=60)
    available = models.BooleanField("disponible", default=True)

    class Meta:
        verbose_name = "aderezo"
        verbose_name_plural = "aderezos"

    def __str__(self):
        return self.name


class Extra(DiscountedPrice):
    name = models.CharField("nombre", max_length=60)
    price = models.PositiveIntegerField("precio")
    available = models.BooleanField("disponible", default=True)

    class Meta:
        constraints = DiscountedPrice.Meta.constraints
        verbose_name = "extra"
        verbose_name_plural = "extras"

    def __str__(self):
        return f"{self.name} (+${self.price})"


class Product(DiscountedPrice):
    class Category(models.TextChoices):
        DRINK = "drink", "Bebida"
        SIDE = "side", "Acompañamiento"

    name = models.CharField("nombre", max_length=80)
    description = models.CharField("descripción", max_length=250, blank=True)
    category = models.CharField("categoría", max_length=10, choices=Category.choices)
    price = models.PositiveIntegerField("precio", null=True, blank=True, validators=[MinValueValidator(1)],
                                        help_text="Completá el precio antes de habilitar la venta.")
    available = models.BooleanField("disponible", default=False)
    photo = models.ImageField("foto", upload_to=product_photo_path, blank=True,
                              validators=[validate_burger_photo], help_text="JPG, PNG o WebP. Máximo 5 MB.")
    suggested = models.BooleanField("sugerir antes de pagar", default=False)
    order = models.PositiveIntegerField("orden", default=0, help_text="Los números menores aparecen primero.")

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "bebida o acompañamiento"
        verbose_name_plural = "bebidas y acompañamientos"
        constraints = DiscountedPrice.Meta.constraints + [
            models.CheckConstraint(condition=models.Q(price__isnull=True) | models.Q(price__gte=1), name="product_positive_price"),
            models.CheckConstraint(condition=models.Q(available=False) | (models.Q(price__isnull=False) & models.Q(price__gte=1)), name="available_product_has_price"),
        ]

    def clean(self):
        super().clean()
        if self.available and (self.price is None or self.price < 1):
            raise ValidationError({"price": "Definí un precio mayor que cero antes de habilitar el producto."})

    def __str__(self):
        return self.name


class AboutPhoto(models.Model):
    caption = models.CharField("texto que acompaña la foto", max_length=300, blank=True,
                               help_text="Una frase breve para contar lo que se ve en la imagen.")
    title = models.CharField("descripción de la foto", max_length=120,
                             help_text="Por ejemplo: salón del local o nuestra parrilla. También sirve como texto accesible.")
    photo = models.ImageField("foto", upload_to=about_photo_path, validators=[validate_burger_photo],
                              help_text="JPG, PNG o WebP. Máximo 5 MB y 16 megapíxeles.")
    active = models.BooleanField("visible", default=True)
    order = models.PositiveIntegerField("orden", default=0, help_text="La primera foto será la principal. Se muestran hasta 6 fotos.")

    class Meta:
        ordering = ["order", "pk"]
        verbose_name = "foto de Nosotros"
        verbose_name_plural = "fotos de Nosotros"

    def __str__(self):
        return self.title


class Order(models.Model):
    class Fulfillment(models.TextChoices):
        PICKUP = "pickup", "Retiro en el local"
        DELIVERY = "delivery", "Entrega a domicilio"

    class Status(models.TextChoices):
        NEW = "new", "Nuevo"
        PREPARING = "preparing", "En preparación"
        READY = "ready", "Listo"
        COMPLETED = "completed", "Entregado"
        CANCELLED = "cancelled", "Cancelado"

    checkout_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField("fecha", auto_now_add=True)
    customer_name = models.CharField("nombre", max_length=100)
    phone = models.CharField("teléfono", max_length=30)
    fulfillment = models.CharField("modalidad", max_length=10, choices=Fulfillment.choices)
    address = models.CharField("dirección", max_length=250, blank=True)
    locality = models.CharField("localidad", max_length=100, blank=True)
    reference = models.CharField("referencias", max_length=250, blank=True)
    delivery_latitude = models.DecimalField("latitud de entrega", max_digits=10, decimal_places=7, null=True, blank=True)
    delivery_longitude = models.DecimalField("longitud de entrega", max_digits=11, decimal_places=7, null=True, blank=True)
    delivery_distance_m = models.PositiveIntegerField("distancia en línea recta (metros)", null=True, blank=True)
    products_total = models.PositiveIntegerField("total de productos")
    delivery_fee = models.PositiveIntegerField("costo de envío", null=True, blank=True)
    total = models.PositiveIntegerField("total final", null=True, blank=True)
    payment_status = models.CharField("estado del pago", max_length=15, default="pending",
                                     choices=[("pending", "Pendiente de pago"), ("paid", "Pagado"),
                                              ("failed", "Rechazado"), ("cancelled", "Cancelado"),
                                              ("refunded", "Reembolsado"), ("review", "Revisar pago")])
    status = models.CharField("preparación", max_length=15, choices=Status.choices, default=Status.NEW)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "pedido"
        verbose_name_plural = "pedidos"

    def __str__(self):
        return f"Pedido #{self.pk} — {self.customer_name}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    burger = models.ForeignKey(Burger, null=True, blank=True, on_delete=models.SET_NULL)
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.SET_NULL)
    product_name = models.CharField("producto", max_length=80)
    quantity = models.PositiveIntegerField("cantidad")
    unit_price = models.PositiveIntegerField("precio unitario con extras")
    subtotal = models.PositiveIntegerField("subtotal")
    aderezos = models.JSONField("aderezos", default=list)
    extras = models.JSONField("extras y precios", default=list)
    notes = models.CharField("aclaraciones", max_length=500, blank=True)

    class Meta:
        verbose_name = "producto del pedido"
        verbose_name_plural = "productos del pedido"

    def __str__(self):
        return f"{self.quantity} × {self.product_name}"


class PaymentAttempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, related_name="payment_attempts", on_delete=models.PROTECT)
    amount = models.PositiveIntegerField("importe")
    environment = models.CharField("entorno", max_length=10, choices=[("test", "Prueba"), ("production", "Producción")])
    provider_order_id = models.CharField("order de Mercado Pago", max_length=100, unique=True, null=True, blank=True)
    checkout_url = models.URLField(max_length=1500, blank=True)
    status = models.CharField("estado", max_length=15, default="created", choices=[
        ("created", "Creado"), ("pending", "Pendiente"), ("paid", "Pagado"),
        ("failed", "Rechazado"), ("cancelled", "Cancelado"),
        ("refunded", "Reembolsado"), ("review", "Revisar pago"),
    ])
    provider_status = models.CharField(max_length=50, blank=True)
    provider_updated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "intento de pago"
        verbose_name_plural = "intentos de pago"

    def __str__(self):
        return f"Pago del pedido #{self.order_id} · {self.get_status_display()}"
