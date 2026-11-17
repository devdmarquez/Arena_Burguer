"""Importación inicial, sin sobrescribir fotos elegidas desde administración."""
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from menu.models import Burger
from menu.images import validate_burger_photo


class Command(BaseCommand):
    help = "Copia las fotos estáticas existentes a los productos que todavía no tienen foto."

    def handle(self, *args, **options):
        count = 0
        for burger in Burger.objects.filter(photo=""):
            filename = slugify(burger.name).replace("-", "_") + ".jpeg"
            source = settings.BASE_DIR / "menu" / "static" / "menu" / "burgers" / filename
            if not source.is_file():
                continue
            photo = ContentFile(source.read_bytes(), name=filename)
            validate_burger_photo(photo)
            burger.photo.save(filename, photo)
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Fotos importadas: {count}."))
