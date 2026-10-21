from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from core.features.inventory.models import InventoryItem
from core.features.pharmacies.models import Pharmacy
from . import tests as base_tests

from datetime import datetime
from zoneinfo import ZoneInfo
from .presentation import opening_state

from core.features.accounts.models import Address
from core.features.notifications.models import Notification

from core.features.reminders.models import Reminder

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
    
    def test_standard_form_validation_and_redirect(self):
        # Check address form validation
        self.client.force_login(self.patient)
        url = reverse('resource_create', args=['addresses'])

        response = self.client.get(url)
        self.assertContains(response, '<form')
        self.assertContains(response, '<html')

        # Missing fields should show an error
        response = self.client.post(url, {'label': 'Home'})
        self.assertContains(response, 'This field is required.')

        # A valid address should be saved
        response = self.client.post(url, {
            'label': 'Office',
            'street': '2 Main',
            'city': 'Test',
            'state': 'Test',
            'postal_code': '123'
        })

        self.assertRedirects(response, '/app/addresses/')
        self.assertTrue(
            Address.objects.filter(user=self.patient, label='Office').exists()
        )

    def test_prescription_file_access_is_scoped(self):
        # Patient can access their prescription file
        self.client.force_login(self.patient)

        response = self.client.get(
            reverse('prescription_file', args=[self.rx.pk])
        )
        self.assertEqual(response.status_code, 200)
        response.close()

        # Another user cannot access the file
        self.client.force_login(self.users['driver'])

        response = self.client.get(
            reverse('prescription_file', args=[self.rx.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_notification_read_all_only_updates_current_user(self):
        # Create notifications for two different users
        own = Notification.objects.create(
            user=self.patient,
            kind='order',
            title='Own',
            body='Own'
        )

        other = Notification.objects.create(
            user=self.users['driver'],
            kind='order',
            title='Other',
            body='Other'
        )

        self.client.force_login(self.patient)
        self.client.post(reverse('notifications_read_all'))

        own.refresh_from_db()
        other.refresh_from_db()

        # Only the patient's notification should be marked as read
        self.assertIsNotNone(own.read_at)
        self.assertIsNone(other.read_at)

    
    def test_reminder_toggle_and_ownership(self):
        # Create a reminder for the patient
        reminder = Reminder.objects.create(
            patient=self.patient,
            medication_name='Test',
            dosage='1 tablet',
            frequency='Daily',
            times=['08:00'],
            start_date='2026-10-15'
        )

        self.client.force_login(self.patient)

        url = reverse(
            'resource_action',
            args=['reminders', reminder.pk, 'toggle']
        )

        # Patient can disable their reminder
        self.client.post(url)
        reminder.refresh_from_db()
        self.assertFalse(reminder.active)

        # Another user cannot change the reminder
        self.client.force_login(self.users['driver'])
        self.assertEqual(self.client.post(url).status_code, 404)

    def test_catalogue_profile_and_filters_render(self):
        # Check pharmacy catalogue and profile pages
        self.client.force_login(self.patient)

        self.assertContains(
            self.client.get(reverse('catalogue', args=[self.pharmacy.pk])),
            'medication-card'
        )

        self.assertContains(
            self.client.get(
                reverse('catalogue', args=[self.pharmacy.pk]),
                {'view': 'profile'}
            ),
            'Pharmacy Information'
        )

        # A missing category should show no medication cards
        self.assertNotContains(
            self.client.get(
                reverse('catalogue', args=[self.pharmacy.pk]),
                {'category': 'Missing'}
            ),
            'class="card medication-card'
        )

    def test_reminder_time_input_accepts_human_readable_times(self):
        from .forms import resource_form

        # Check that comma-separated times are accepted
        self.client.force_login(self.patient)

        response = self.client.post(
            reverse('resource_create', args=['reminders']),
            {
                'medication_name': 'Morning medicine',
                'dosage': '1 tablet',
                'frequency': 'Daily',
                'times': '08:00, 20:00',
                'start_date': '2026-10-15',
                'active': 'on'
            }
        )

        self.assertEqual(response.status_code, 302)

        # Times should be saved as a list
        reminder = Reminder.objects.get(
            medication_name='Morning medicine'
        )
        self.assertEqual(reminder.times, ['08:00', '20:00'])

        # Check that the form displays the saved times
        form = resource_form(
            'reminders',
            self.patient,
            instance=reminder
        )
        self.assertIn('08:00, 20:00', str(form['times']))

    
    def test_prescription_review_dialog_validates_and_saves(self):
        # Check prescription review permissions and validation
        self.rx.status = 'pending'
        self.rx.save()

        url = reverse('review_prescription', args=[self.rx.pk])

        # Patients should not be allowed to review prescriptions
        self.client.force_login(self.patient)
        self.assertEqual(self.client.get(url).status_code, 403)

        # Pharmacists should be able to access the review form
        self.client.force_login(self.users['pharmacist'])
        self.assertContains(self.client.get(url), 'Review Prescription')

        # Negative refill values should be rejected
        response = self.client.post(url, {
            'status': 'approved',
            'kind': 'repeat',
            'refills_remaining': -1
        })

        self.assertContains(
            response,
            'Ensure this value is greater than or equal to 0.'
        )

        # Valid review information should be saved
        response = self.client.post(url, {
            'status': 'approved',
            'kind': 'repeat',
            'refills_remaining': 3,
            'review_notes': 'Reviewed'
        })

        self.assertRedirects(response, '/app/prescriptions/')

        self.rx.refresh_from_db()
        self.assertEqual(self.rx.refills_remaining, 3)

    def test_driver_session_availability_can_be_toggled(self):
        # Only drivers can change their availability
        self.client.force_login(self.patient)
        self.assertEqual(
            self.client.post('/driver/availability/').status_code,
            403
        )

        self.client.force_login(self.users['driver'])

        # Driver should initially be online
        self.assertContains(
            self.client.get('/app/overview/'),
            'You are online.'
        )

        # GET requests should not change availability
        self.assertEqual(
            self.client.get('/driver/availability/').status_code,
            405
        )

        # Switch driver to offline
        self.client.post('/driver/availability/')
        self.assertFalse(self.client.session['driver_online'])

        response = self.client.get('/app/overview/')
        self.assertContains(response, 'You are offline.')
        self.assertNotContains(response, 'Orders Available for Delivery')

        # Switch driver back to online
        self.client.post('/driver/availability/')
        self.assertTrue(self.client.session['driver_online'])

        self.assertContains(
            self.client.get('/app/overview/'),
            'Orders Available for Delivery'
        )

