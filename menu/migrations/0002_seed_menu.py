from django.db import migrations

BURGERS = [
    ("Arena Clásica", "Carne 180g, queso cheddar, lechuga, tomate y salsa de la casa.", 8500),
    ("Fuego Doble", "Doble carne, doble cheddar, bacon crocante y salsa BBQ ahumada.", 11900),
    ("Brasa Picante", "Carne, jalapeños, pepper jack, cebolla caramelizada y mayo picante.", 10200),
    ("Gladiador", "Triple carne, huevo, bacon, cheddar y aros de cebolla.", 13500),
]
ADEREZOS = ["Ketchup", "Mayonesa", "Mostaza", "Salsa BBQ", "Salsa picante", "Alioli"]
EXTRAS = [
    ("Bacon extra", 1500),
    ("Huevo", 800),
    ("Cheddar extra", 700),
    ("Cebolla caramelizada", 600),
    ("Porción de papas", 2500),
]


def seed(apps, schema_editor):
    Burger = apps.get_model("menu", "Burger")
    Aderezo = apps.get_model("menu", "Aderezo")
    Extra = apps.get_model("menu", "Extra")
    for i, (n, d, p) in enumerate(BURGERS):
        Burger.objects.create(name=n, description=d, price=p, order=i)
    for n in ADEREZOS:
        Aderezo.objects.create(name=n)
    for n, p in EXTRAS:
        Extra.objects.create(name=n, price=p)


class Migration(migrations.Migration):
    dependencies = [("menu", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
