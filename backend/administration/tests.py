from django.apps import apps
from django.test import TestCase
from django.urls import resolve

from core.models import User


class AppStructureTests(TestCase):

    def test_only_two_project_apps(self):
        # Get the project apps
        project_apps = [
            config.name
            for config in apps.get_app_configs()
            if config.name in {'core', 'administration'}
            or config.name.startswith('core.')
        ]

        # Check that only core and administration are registered
        self.assertEqual(project_apps, ['core', 'administration'])

        # All core models should belong to the core app
        self.assertTrue(
            all(
                model._meta.app_label == 'core'
                for model in apps.get_app_config('core').get_models()
            )
        )

        # Administration should not have its own models
        self.assertFalse(
            list(apps.get_app_config('administration').get_models())
        )

    def test_administrator_routes_are_owned_by_administration(self):
        # Check that administrator URLs use administration views
        for url in [
            '/administrator/',
            '/staff/invite/',
            '/reports/orders.csv'
        ]:
            self.assertEqual(
                resolve(url).func.__module__,
                'administration.views'
            )

    def test_administrator_portal_enforces_role(self):
        # Create a patient account
        patient = User.objects.create_user(
            email='patient@structure.test',
            password='test',
            role='patient'
        )

        # Patients should not access the administrator portal
        self.client.force_login(patient)
        self.assertEqual(
            self.client.get('/administrator/').status_code,
            403
        )

        # Create an administrator account
        administrator = User.objects.create_superuser(
            email='admin@structure.test',
            password='test'
        )

        # Administrators should be able to access both admin pages
        self.client.force_login(administrator)
        self.assertEqual(
            self.client.get('/administrator/').status_code,
            200
        )
        self.assertEqual(
            self.client.get('/admin/').status_code,
            200
        )
