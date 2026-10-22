from django.contrib.auth.tokens import default_token_generator
from django.test import Client, TestCase
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from core.models import User
from . import tests as website_tests


class AuthenticationViewTests(TestCase):
    setUp = website_tests.NativeWebsiteTests.setUp

    def test_password_reset_keeps_token_validation_password_change_and_login(self):
        uid = urlsafe_base64_encode(force_bytes(self.patient.pk))
        token = default_token_generator.make_token(self.patient)
        url = reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        form_url = response.url
        self.assertContains(self.client.get(form_url), 'name="new_password1"')
        response = self.client.post(form_url, {'new_password1': 'New-Password-26!', 'new_password2': 'Mismatch'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        password = 'PillPal-Updated-Password-26!'
        self.assertRedirects(self.client.post(form_url, {'new_password1': password, 'new_password2': password}),
                             reverse('password_reset_complete'))
        self.patient.refresh_from_db()
        self.assertTrue(self.patient.check_password(password))
        fresh_client = Client()
        self.assertContains(fresh_client.get(url), 'expired or is invalid')
        self.assertRedirects(self.client.post('/auth', {'username': self.patient.email, 'password': password}),
                             reverse('dashboard'))

    def test_public_authentication_and_reset_posts_still_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        for url in ['/auth', '/auth?mode=register', '/password-reset/']:
            self.assertEqual(client.post(url, {}).status_code, 403)

    def test_invalid_login_and_registration_preserve_form_errors_without_creating_users(self):
        response = self.client.post('/auth', {'username': self.patient.email, 'password': 'wrong'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        self.assertNotIn('_auth_user_id', self.client.session)
        before = User.objects.count()
        response = self.client.post('/auth?mode=register', {'email': self.patient.email,
            'first_name': 'Test', 'last_name': 'Patient', 'password': '123'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        self.assertEqual(User.objects.count(), before)
