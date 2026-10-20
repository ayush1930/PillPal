from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from core.models import Medication, Pharmacy, InventoryItem
from core.web import tests as website_tests
from .services import add_inventory


class ManualInventoryTests(TestCase):
    setUp = website_tests.NativeWebsiteTests.setUp

    def data(self):
        return dict(pharmacy=self.pharmacy, supplier=None, price=Decimal('6.00'), quantity=3,
            reorder_level=2, name='Manual medication', generic_name='Generic', brand='',
            category='General', dosage_form='', requires_prescription=False)

    def test_manual_product_creation_and_existing_product_restock(self):
        data = self.data()
        item = add_inventory(actor=self.users['pharmacist'], **data)
        self.assertEqual(item.stock, 3)
        data.update(medication=item.medication, name='Do not overwrite catalogue')
        repeated = add_inventory(actor=self.users['pharmacist'], **data)
        self.assertEqual(item.pk, repeated.pk)
        self.assertEqual(repeated.stock, 6)
        self.assertEqual(repeated.medication.name, 'Manual medication')

    def test_manual_intake_page_has_no_hardware_controls_and_saves(self):
        self.client.force_login(self.users['pharmacist'])
        response = self.client.get('/inventory/add/')
        self.assertContains(response, 'Existing medication')
        for text in ['barcode', 'scanner', 'Use Camera', 'getUserMedia']:
            self.assertNotContains(response, text)
        data = self.data(); data.update(pharmacy=self.pharmacy.pk, supplier='')
        self.assertRedirects(self.client.post('/inventory/add/', data), '/app/inventory/')
        self.assertTrue(InventoryItem.objects.filter(medication__name='Manual medication').exists())

    def test_staff_cannot_add_to_another_pharmacy_and_patient_cannot_add_stock(self):
        data = self.data()
        data['pharmacy'] = Pharmacy.objects.create(name='Other', address='Elsewhere', phone='123')
        with self.assertRaises(PermissionDenied):
            add_inventory(actor=self.users['pharmacist'], **data)
        self.client.force_login(self.patient)
        self.assertEqual(self.client.get('/inventory/add/').status_code, 403)
        self.assertEqual(self.client.post('/inventory/add/', {}).status_code, 403)

    def test_invalid_quantities_create_nothing(self):
        for quantity in [0, -1, 1.5, True]:
            data = self.data(); data['quantity'] = quantity
            with self.assertRaises(ValidationError):
                add_inventory(actor=self.users['pharmacist'], **data)
        self.assertFalse(Medication.objects.filter(name='Manual medication').exists())

    def test_existing_catalogue_item_can_be_selected_without_reentering_details(self):
        self.client.force_login(self.users['pharmacist'])
        response = self.client.post('/inventory/add/', dict(medication=self.medication.pk,
            pharmacy=self.pharmacy.pk, price='10', quantity=2, reorder_level=5))
        self.assertRedirects(response, '/app/inventory/')
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.stock, 12)
