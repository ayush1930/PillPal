from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from core.features.accounts.models import User
from core.features.inventory.models import InventoryItem, ReorderRequest
from core.features.inventory.services import change_reorder_status
from core.features.notifications.models import Notification
from core.features.orders.models import Order
from core.features.orders.services import place_order, accept_delivery, complete_order, change_order_status
from core.features.payments.services import record_cash_payment
from core.web import tests as website_tests
from core.web.forms import RegistrationForm, InvitationForm, resource_form


class SemesterOneWorkflowTests(TestCase):
    setUp = website_tests.NativeWebsiteTests.setUp

    def checkout(self, **overrides):
        options = dict(patient=self.patient, cart={str(self.stock.pk): 2},
                       delivery_type='delivery', address=self.address, prescription=self.rx)
        options.update(overrides)
        return place_order(**options)

    def prepare(self, order):
        for status in ['processing', 'ready']:
            change_order_status(order_id=order.pk, actor=self.users['pharmacist'], status=status)

    def test_django_only_dependencies_and_no_json_endpoints(self):
        from django.conf import settings
        self.assertNotIn('rest_framework', settings.INSTALLED_APPS)
        self.assertNotIn('corsheaders', settings.INSTALLED_APPS)
        self.assertFalse(hasattr(settings, 'REST_FRAMEWORK'))
        for path in ['/api/', '/api/orders/', '/api/auth/login/']:
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_delivery_completion_and_cash_collection(self):
        order = self.checkout()
        self.assertEqual(order.total, Decimal('24.99'))
        self.prepare(order)
        accept_delivery(order_id=order.pk, actor=self.users['driver'])
        complete_order(order_id=order.pk, actor=self.users['driver'])
        record_cash_payment(order_id=order.pk, actor=self.users['driver'])
        order.refresh_from_db(); self.rx.refresh_from_db()
        self.assertEqual(order.status, 'delivered')
        self.assertTrue(order.cash_collected)
        self.assertTrue(self.rx.is_voided)
        self.assertEqual(Notification.objects.filter(user=self.patient).count(), 5)

    def test_pickup_is_completed_by_own_pharmacy(self):
        order = self.checkout(delivery_type='pickup', address=None)
        self.assertEqual(order.delivery_fee, 0)
        self.prepare(order)
        with self.assertRaises(PermissionDenied):
            complete_order(order_id=order.pk, actor=self.users['driver'])
        self.client.force_login(self.users['pharmacist'])
        self.assertContains(self.client.get(f'/orders/{order.pk}/'), 'Confirm Pickup')
        self.client.post(f'/manage/orders/{order.pk}/deliver/')
        self.client.post(f'/manage/orders/{order.pk}/paid/')
        order.refresh_from_db()
        self.assertEqual(order.status, 'delivered')
        self.assertTrue(order.cash_collected)

    def test_cancel_restores_stock_exactly_once(self):
        order = self.checkout()
        self.stock.refresh_from_db(); self.assertEqual(self.stock.stock, 8)
        change_order_status(order_id=order.pk, actor=self.users['pharmacist'], status='cancelled')
        with self.assertRaises(ValidationError):
            change_order_status(order_id=order.pk, actor=self.users['pharmacist'], status='cancelled')
        self.stock.refresh_from_db(); self.assertEqual(self.stock.stock, 10)

    def test_late_stock_failure_rolls_back_order_and_all_items(self):
        from core.features.medications.models import Medication
        medication = Medication.objects.create(name='Second', generic_name='Second', category='General')
        stock = InventoryItem.objects.create(pharmacy=self.pharmacy, medication=medication, price=2, stock=0)
        with self.assertRaises(ValidationError):
            self.checkout(cart={str(self.stock.pk): 2, str(stock.pk): 1})
        self.assertFalse(Order.objects.exists())
        self.stock.refresh_from_db(); self.assertEqual(self.stock.stock, 10)
        self.assertFalse(Notification.objects.exists())

    def test_prices_recalculated_and_invalid_quantities_rejected(self):
        self.stock.price = Decimal('12.00'); self.stock.save()
        for quantity in [-1, 0, 1.5, True]:
            with self.assertRaises(ValidationError):
                self.checkout(cart={str(self.stock.pk): quantity})
        self.assertEqual(self.checkout().total, Decimal('28.99'))

    def test_prescription_cannot_have_two_active_orders(self):
        self.checkout()
        with self.assertRaisesMessage(ValidationError, 'active order'):
            self.checkout()
        self.assertEqual(Order.objects.count(), 1)

    def test_repeat_prescription_decrements_once_on_completion(self):
        self.rx.kind = 'repeat'; self.rx.refills_remaining = 1; self.rx.save()
        order = self.checkout(delivery_type='pickup', address=None)
        self.prepare(order)
        complete_order(order_id=order.pk, actor=self.users['pharmacist'])
        with self.assertRaises(ValidationError):
            complete_order(order_id=order.pk, actor=self.users['pharmacist'])
        self.rx.refresh_from_db(); self.assertEqual(self.rx.refills_remaining, 0)
        with self.assertRaisesMessage(ValidationError, 'no available refills'):
            self.checkout()

    def test_driver_cannot_complete_or_take_another_drivers_order(self):
        order = self.checkout(); self.prepare(order)
        accept_delivery(order_id=order.pk, actor=self.users['driver'])
        other = User.objects.create_user(email='driver2@example.com', role='driver')
        with self.assertRaises(ValidationError):
            accept_delivery(order_id=order.pk, actor=other)
        with self.assertRaises(PermissionDenied):
            complete_order(order_id=order.pk, actor=other)

    def test_cash_requires_completion_and_staff_permission(self):
        order = self.checkout()
        with self.assertRaises(PermissionDenied):
            record_cash_payment(order_id=order.pk, actor=self.patient)
        with self.assertRaises(ValidationError):
            record_cash_payment(order_id=order.pk, actor=self.users['admin'])

    def test_received_reorder_adds_stock_once(self):
        reorder = ReorderRequest.objects.create(inventory_item=self.stock, requested_by=self.users['pharmacist'], quantity=5)
        for status in ['approved', 'sent', 'received']:
            change_reorder_status(reorder_id=reorder.pk, actor=self.users['pharmacist'], status=status)
        with self.assertRaises(ValidationError):
            change_reorder_status(reorder_id=reorder.pk, actor=self.users['pharmacist'], status='received')
        self.stock.refresh_from_db(); self.assertEqual(self.stock.stock, 15)

    def test_forms_reject_duplicate_email_weak_password_and_bad_dates(self):
        form = RegistrationForm(dict(email=self.patient.email, first_name='Test', last_name='Test', password='123'))
        self.assertFalse(form.is_valid()); self.assertIn('email', form.errors); self.assertIn('password', form.errors)
        form = InvitationForm(dict(email='staff@new.test', first_name='New', last_name='Staff', role='pharmacist'))
        self.assertFalse(form.is_valid()); self.assertIn('pharmacy', form.errors)
        form = resource_form('reminders', self.patient, dict(medication_name='Test', dosage='1', frequency='Daily', times='08:00', start_date='2026-10-17', end_date='2026-10-16'))
        self.assertFalse(form.is_valid()); self.assertIn('end_date', form.errors)

    def test_direct_media_url_does_not_bypass_prescription_permissions(self):
        url = '/media/' + self.rx.file.name
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.users['driver'])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.patient)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200); response.close()

    def test_password_reset_uses_django_email_and_html(self):
        from django.core import mail
        with self.settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'):
            response = self.client.post('/password-reset/', {'email': self.patient.email})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(len(mail.outbox), 1)
            self.assertIn('/password-reset/', mail.outbox[0].body)

    def test_optional_demo_command_does_not_overwrite_existing_accounts(self):
        from unittest.mock import patch
        from io import StringIO
        from django.core.management import call_command
        from core.models import Pharmacy
        password = 'PillPal-Demo-Strong-Password-26!'
        with patch('core.management.commands.seed_demo.getpass', return_value=password):
            call_command('seed_demo', stdout=StringIO())
        admin = User.objects.get(email='demo.admin@example.test')
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.check_password(password))
        with patch('core.management.commands.seed_demo.getpass', return_value='Another-Strong-Password-26!'):
            call_command('seed_demo', stdout=StringIO())
        admin.refresh_from_db()
        self.assertTrue(admin.check_password(password))
        self.assertEqual(Pharmacy.objects.filter(name='PillPal Demo Pharmacy').count(), 1)
