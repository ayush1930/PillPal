from getpass import getpass

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import User, Pharmacy, PharmacyStaff, Medication, InventoryItem, Supplier


class Command(BaseCommand):
    help = 'Create optional local demo accounts and pharmacy stock; existing records are not overwritten.'

    def handle(self, *args, **options):
        password = getpass('Choose a password for new demo accounts: ')
        if password != getpass('Confirm password: '):
            raise CommandError('Passwords do not match.')
        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError('; '.join(exc.messages))
        with transaction.atomic():
            users = {}
            for role in User.Role.values:
                email = f'demo.{role}@example.test'
                user = User.objects.filter(email=email).first()
                if user and user.role != role:
                    raise CommandError(f'{email} already has a different role. No changes saved.')
                if not user:
                    creator = User.objects.create_superuser if role == 'admin' else User.objects.create_user
                    user = creator(email=email, password=password, role=role, first_name='Demo', last_name=role.title())
                users[role] = user
            pharmacy, _ = Pharmacy.objects.get_or_create(name='PillPal Demo Pharmacy', defaults={
                'address': 'Demo address — replace before real use', 'phone': '0000000000',
                'opening_hours': {'always_open': True}, 'delivery_available': True})
            PharmacyStaff.objects.get_or_create(pharmacy=pharmacy, user=users['pharmacist'])
            supplier, _ = Supplier.objects.get_or_create(name='Demo Supplier')
            for name, price, prescription in [('Demo OTC item', '5.00', False), ('Demo prescription item', '10.00', True)]:
                medication, _ = Medication.objects.get_or_create(name=name, defaults={
                    'generic_name': name, 'category': 'Demonstration', 'requires_prescription': prescription})
                InventoryItem.objects.get_or_create(pharmacy=pharmacy, medication=medication, defaults={
                    'supplier': supplier, 'price': price, 'stock': 20, 'reorder_level': 5})
        self.stdout.write(self.style.SUCCESS('Demo records ready. Existing passwords and stock were not changed.'))
        for user in users.values():
            self.stdout.write(f'{user.role}: {user.email}')
