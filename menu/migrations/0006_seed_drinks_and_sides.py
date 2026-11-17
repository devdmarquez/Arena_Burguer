from django.db import migrations


def seed(apps, schema_editor):
    alias = schema_editor.connection.alias
    Product = apps.get_model("menu", "Product")
    products = [
        ("Papas fritas", "Porción de papas fritas", "side", 5000),
        ("Coca-Cola 600 ml", "Botella de 600 ml", "drink", 2500),
        ("Sprite 600 ml", "Botella de 600 ml", "drink", 2500),
        ("Fanta 600 ml", "Botella de 600 ml", "drink", 2500),
    ]
    for order, (name, description, category, price) in enumerate(products):
        Product.objects.using(alias).get_or_create(name=name, defaults={
            "description": description, "category": category, "price": price,
            "available": True, "suggested": True, "order": order,
        })
    # Las papas pasan a ser un acompañamiento independiente, sin duplicar la oferta.
    Extra = apps.get_model("menu", "Extra")
    Extra.objects.using(alias).filter(name="Porción de papas").update(available=False)
    # Mantener el acceso al catálogo de las cuentas del dueño ya configuradas.
    Group = apps.get_model("auth", "Group")
    group = Group.objects.using(alias).filter(name="Dueño del local").first()
    if group:
        ContentType = apps.get_model("contenttypes", "ContentType")
        Permission = apps.get_model("auth", "Permission")
        ct, _ = ContentType.objects.using(alias).get_or_create(app_label="menu", model="product")
        for action in ("add", "change", "delete", "view"):
            permission, _ = Permission.objects.using(alias).get_or_create(content_type=ct,
                codename=f"{action}_product", defaults={"name": f"Can {action} product"})
            group.permissions.add(permission)


class Migration(migrations.Migration):
    dependencies = [("menu", "0005_product_orderitem_product")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
