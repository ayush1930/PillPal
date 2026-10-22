import os
from django.core.management.base import BaseCommand

from core.features.accounts.models import User


class Command(BaseCommand):
    help = "Create or update the master PillPal administrator from environment variables."

    def handle(self, *args, **options):
        email = os.environ.get("PILLPAL_ADMIN_EMAIL", "admin@pillpal.com")
        password = os.environ.get("PILLPAL_ADMIN_PASSWORD")
        if not password:
            self.stderr.write("Set PILLPAL_ADMIN_PASSWORD before running this command.")
            return
        user, _ = User.objects.get_or_create(email=email)
        user.role = User.Role.ADMIN
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS(f"Administrator ready: {email}"))
