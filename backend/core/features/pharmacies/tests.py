from decimal import Decimal

from django.test import Client, TestCase
from core.models import Pharmacy
from core.web import tests as website_tests
from core.web.forms import resource_form
from .services import distance_km


class SavedCoordinateTests(TestCase):
    setUp = website_tests.NativeWebsiteTests.setUp

    # Test if pharmacies are sorted by distance
    def test_distance_sort_and_display_use_saved_default_address(self):
        self.address.latitude = 0
        self.address.longitude = 0
        self.address.is_default = True
        self.address.save()

        self.pharmacy.latitude = 0
        self.pharmacy.longitude = 2
        self.pharmacy.save()

        close = Pharmacy.objects.create(
            name="Closer",
            address="Near",
            phone="123",
            latitude=0,
            longitude=1
        )

        unknown = Pharmacy.objects.create(
            name="Unknown distance",
            address="Unknown",
            phone="123"
        )

        self.client.force_login(self.patient)

        response = self.client.get(
            "/app/pharmacies/",
            {"sort": "distance"}
        )

        # Check if pharmacies are sorted correctly
        expected = [close.pk, self.pharmacy.pk, unknown.pk]
        actual = [item.pk for item in response.context["pharmacies"]]

        self.assertEqual(actual, expected)
        self.assertContains(response, "30.0 km")
        self.assertContains(response, "Straight-line distance")

    # Test missing, zero and invalid coordinates
    def test_distance_does_not_invent_missing_coordinates_and_handles_zero(self):
        self.assertIsNone(distance_km(self.pharmacy, self.address))

        self.address.latitude = Decimal("0")
        self.pharmacy.latitude = Decimal("0")
        self.address.longitude = Decimal("0")
        self.pharmacy.longitude = Decimal("0")

        self.assertEqual(distance_km(self.pharmacy, self.address), 0)

        # Latitude cannot be greater than 90
        self.pharmacy.latitude = Decimal("91")
        self.assertIsNone(distance_km(self.pharmacy, self.address))

    # Test coordinate validation in the address form
    def test_address_coordinate_form_validates_ranges_and_pairs(self):
        data = {
            "label": "Home",
            "street": "1 Main",
            "city": "Test",
            "state": "Test",
            "postal_code": "123",
            "latitude": "-20.160891",
            "longitude": "57.501222"
        }

        form = resource_form("addresses", self.patient, data)
        self.assertTrue(form.is_valid(), form.errors)

        # Test invalid latitude
        data["latitude"] = "91"
        form = resource_form("addresses", self.patient, data)

        self.assertFalse(form.is_valid())
        self.assertIn("latitude", form.errors)

        # Test when longitude is missing
        data["latitude"] = "-20"
        data["longitude"] = ""

        form = resource_form("addresses", self.patient, data)
        self.assertFalse(form.is_valid())

    # Test driver availability and CSRF protection
    def test_driver_toggle_requires_csrf_and_does_not_modify_other_sessions(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.users["driver"])

        # Request without CSRF token should be rejected
        response = client.post("/driver/availability/")
        self.assertEqual(response.status_code, 403)

        # Update driver availability
        self.client.force_login(self.users["driver"])
        self.client.post("/driver/availability/")

        # Check availability from another session
        second = Client()
        second.force_login(self.users["driver"])

        response = second.get("/app/overview/")
        self.assertContains(response, "You are online.")
