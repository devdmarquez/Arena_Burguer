from getpass import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Crea o habilita una cuenta del dueño con permisos de pedidos y catálogo. La contraseña se ingresa en la terminal."

    def add_arguments(self, parser):
        parser.add_argument("username")

    def handle(self, *args, **options):
        User = get_user_model()
        username = options["username"].strip()
        if not username:
            raise CommandError("Ingresá un nombre de usuario.")
        user = User.objects.filter(username=username).first()
        if user and user.is_superuser:
            raise CommandError("Esta cuenta ya es superusuario y puede ingresar al panel. Elegí otro usuario para una cuenta limitada.")
        if user and not user.is_active:
            raise CommandError("La cuenta está desactivada. Revisala antes de habilitarla.")
        if user is None:
            user = User(username=username)
            password = getpass("Contraseña de la cuenta del dueño: ")
            if password != getpass("Repetir contraseña: "):
                raise CommandError("Las contraseñas no coinciden.")
            try:
                validate_password(password, user=user)
                user.set_password(password)
                user.full_clean(exclude=["password"])
            except ValidationError as exc:
                raise CommandError(" ".join(exc.messages)) from exc
        codes = {"view_order", "change_order"}
        codes.update(f"{action}_{model}" for model in ("burger", "aderezo", "extra", "product", "aboutphoto")
                     for action in ("add", "change", "delete", "view"))
        with transaction.atomic():
            group, _ = Group.objects.get_or_create(name="Dueño del local")
            group.permissions.set(Permission.objects.filter(content_type__app_label="menu", codename__in=codes))
            user.is_staff = True
            user.save()
            user.groups.add(group)
        self.stdout.write(self.style.SUCCESS(f"Cuenta {username} habilitada para /gestion/pedidos/ y administración del menú."))
