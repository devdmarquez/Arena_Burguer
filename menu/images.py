from pathlib import PurePath
import uuid
import warnings

from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError


def burger_photo_path(instance, filename):
    # Independiente del nombre del producto, sin colisiones ni caché de la foto anterior.
    return f"hamburguesas/{uuid.uuid4().hex}{PurePath(filename).suffix.lower()}"


def product_photo_path(instance, filename):
    return f"productos/{uuid.uuid4().hex}{PurePath(filename).suffix.lower()}"


def about_photo_path(instance, filename):
    return f"nosotros/{uuid.uuid4().hex}{PurePath(filename).suffix.lower()}"


def validate_burger_photo(value):
    if value.size > 5 * 1024 * 1024:
        raise ValidationError("La foto debe pesar como máximo 5 MB.")
    formats = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}
    expected = formats.get(PurePath(value.name).suffix.lower())
    if not expected:
        raise ValidationError("Elegí una foto JPG, PNG o WebP.")
    try:
        value.seek(0)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(value) as photo:
                if photo.format != expected:
                    raise ValidationError("El contenido de la foto no coincide con su extensión.")
                if photo.width * photo.height > 16_000_000:
                    raise ValidationError("La foto debe tener como máximo 16 megapíxeles.")
                if getattr(photo, "is_animated", False):
                    raise ValidationError("Elegí una foto sin animación.")
                photo.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise ValidationError("No se pudo leer la foto. Elegí una imagen JPG, PNG o WebP válida.") from exc
    finally:
        value.seek(0)
