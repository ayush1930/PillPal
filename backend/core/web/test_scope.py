from django.conf import settings
from django.test import TestCase

from core.models import Address, Medication, Pharmacy
from core.web import tests as website_tests
from core.web.forms import resource_form


class SemesterOneScopeTests(TestCase):
    # Reuse the test data from the website tests
    setUp = website_tests.NativeWebsiteTests.setUp