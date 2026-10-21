from django.conf import settings
from django.test import TestCase

from core.models import Address, Medication, Pharmacy
from core.web import tests as website_tests
from core.web.forms import resource_form


class SemesterOneScopeTests(TestCase):
    # Reuse the test data from the website tests
    setUp = website_tests.NativeWebsiteTests.setUp

    
    def test_saved_coordinates_are_available_but_barcode_is_not(self):
        # Medications should not have a barcode field
        self.assertNotIn(
            'barcode',
            {field.name for field in Medication._meta.fields}
        )

        # Barcode should not appear in the medication form
        self.assertNotIn(
            'barcode',
            resource_form('medications', self.users['admin']).fields
        )

        # Addresses and pharmacies should have coordinate fields
        for model, resource in [
            (Address, 'addresses'),
            (Pharmacy, 'pharmacies')
        ]:
            self.assertTrue(
                {'latitude', 'longitude'}.issubset(
                    field.name for field in model._meta.fields
                )
            )

            # Coordinates should also appear in their forms
            self.assertTrue(
                {'latitude', 'longitude'}.issubset(
                    resource_form(resource, self.users['admin']).fields
                )
            )

    
    def test_web_pages_present_complete_current_workflows_without_future_controls(self):
        # Pages that should be accessible to each user role
        for role, urls in [
            ('patient', ['/app/pharmacies/', '/app/tracking/']),
            ('pharmacist', ['/app/inventory/', '/inventory/add/']),
            ('driver', ['/app/overview/'])
        ]:
            self.client.force_login(self.users[role])

            # Check that each page loads successfully
            for url in urls:
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

                # Future features should not appear on these pages
                for text in [
                    'Scan Barcode',
                    'Use Camera',
                    'Live Tracking',
                    'Coming soon'
                ]:
                    self.assertNotContains(response, text)

