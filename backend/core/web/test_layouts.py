from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from core.features.inventory.models import InventoryItem
from core.features.pharmacies.models import Pharmacy
from . import tests as base_tests

from datetime import datetime
from zoneinfo import ZoneInfo
from .presentation import opening_state

class RebuiltLayoutTests(TestCase):
    # Use the existing website test data
    setUp = base_tests.NativeWebsiteTests.setUp

    def test_pharmacy_cards_search_and_filters(self):
        # Check pharmacy cards, search and filters
        self.client.force_login(self.patient)

        self.pharmacy.opening_hours = {'always_open': True}
        self.pharmacy.save()

        other = Pharmacy.objects.create(
            name='Pickup Pharmacy',
            address='Elsewhere',
            phone='456',
            delivery_available=False,
            opening_hours={'daily': 'closed'})

        # Check that both pharmacies appear as cards
        response = self.client.get('/app/pharmacies/')
        self.assertContains(response, 'class="card pharmacy-card"', count=2)
        self.assertContains(response, 'Search Medications Across Pharmacies')
        self.assertNotContains(response, '<table>')

        # Filter pharmacies that offer delivery
        response = self.client.get('/app/pharmacies/', {'delivery': '1'})
        self.assertContains(response, self.pharmacy.name)
        self.assertNotContains(response, other.name)

        # Filter pharmacies that are open
        response = self.client.get('/app/pharmacies/', {'open': '1'})
        self.assertContains(response, self.pharmacy.name)
        self.assertNotContains(response, other.name)

        # Search for a pharmacy by name
        response = self.client.get('/app/pharmacies/', {'q': 'Pickup'})
        self.assertContains(response, other.name)
        self.assertNotContains(response, 'Test Pharmacy')

    def test_cross_pharmacy_search_preserves_price_and_pharmacy(self):
        # Check medication prices across different pharmacies
        self.client.force_login(self.patient)

        pharmacy = Pharmacy.objects.create(
            name='Second Pharmacy',
            address='2 Test',
            phone='456'
        )

        InventoryItem.objects.create(
            pharmacy=pharmacy,
            medication=self.medication,
            price=Decimal('6.50'),
            stock=3
        )

        # Check prices and pharmacy link
        response = self.client.get(
            '/app/pharmacies/',
            {'med': 'Test', 'partial': 'medications'}
        )

        self.assertContains(response, '$6.50')
        self.assertContains(response, '$10.00')
        self.assertContains(response, reverse('catalogue', args=[pharmacy.pk]))

        # Inactive pharmacies should not appear in results
        pharmacy.active = False
        pharmacy.save()

        response = self.client.get(
            '/app/pharmacies/',
            {'med': 'Test', 'partial': 'medications'}
        )

        self.assertNotContains(response, '$6.50')


    def test_pharmacy_name_sort_uses_textual_catalogue(self):
        # Check that pharmacies are sorted alphabetically
        self.client.force_login(self.patient)

        first = Pharmacy.objects.create(
            name='A Pharmacy',
            address='1 Main',
            phone='123'
        )

        response = self.client.get('/app/pharmacies/', {'sort': 'name'})

        self.assertEqual(response.context['pharmacies'][0].pk, first.pk)
        self.assertContains(response, 'Distance (Nearest)')

    def test_unknown_hours_do_not_appear_as_open(self):
        # Missing opening hours should not be treated as open
        self.assertIsNone(opening_state(self.pharmacy))

        # Check opening hours that continue past midnight
        self.pharmacy.opening_hours = {
            'daily': {'open': '22:00', 'close': '06:00'}
        }

        self.assertTrue(
            opening_state(
                self.pharmacy,
                datetime(2026, 10, 15, 23, 0, tzinfo=ZoneInfo('UTC'))
            )
        )

        self.assertFalse(
            opening_state(
                self.pharmacy,
                datetime(2026, 10, 15, 12, 0, tzinfo=ZoneInfo('UTC'))
            )
        )
