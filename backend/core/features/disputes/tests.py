from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import resolve, reverse

from core.models import User, Order, Notification
from core.web import tests as website_tests
from .models import Dispute, DisputeUpdate
from .services import submit_dispute, review_dispute, validate_evidence


class DisputeWorkflowTests(TestCase):
    setUp = website_tests.NativeWebsiteTests.setUp

    def order(self, patient=None):
        return Order.objects.create(patient=patient or self.patient, pharmacy=self.pharmacy,
                                    delivery_type='pickup', subtotal=10, total=10)

    def submit(self, **changes):
        data = dict(actor=self.patient, order_id=self.order().pk, subject='Missing item',
                    category='order', description='One item was missing. Please investigate.')
        data.update(changes)
        return submit_dispute(**data)

    def review(self, dispute, **changes):
        data = dict(actor=self.users['admin'], dispute_id=dispute.pk,
                    status='under_review', response='We are investigating.', version=dispute.version)
        data.update(changes)
        return review_dispute(**data)

    def test_patient_submission_from_order_page_creates_history_and_admin_notice(self):
        order = self.order()
        self.client.force_login(self.patient)
        self.assertContains(self.client.get(reverse('order_detail', args=[order.pk])), 'Report a Problem')
        response = self.client.post(reverse('dispute_create'), dict(order=order.pk,
            subject='Late order', category='delivery', description='Please investigate.', status='resolved'))
        dispute = Dispute.objects.get()
        self.assertRedirects(response, reverse('dispute_detail', args=[dispute.pk]))
        self.assertEqual(dispute.status, 'open')
        self.assertEqual(dispute.history.get().actor, self.patient)
        self.assertTrue(Notification.objects.filter(user=self.users['admin'], kind='dispute').exists())

    def test_patient_cannot_submit_for_another_patient(self):
        other = User.objects.create_user(email='other@disputes.test')
        order = self.order(other)
        with self.assertRaises(PermissionDenied):
            self.submit(order_id=order.pk)
        self.client.force_login(self.patient)
        response = self.client.post(reverse('dispute_create'), dict(order=order.pk,
            subject='Foreign', category='order', description='Should be refused.'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Select a valid choice')
        self.assertFalse(Dispute.objects.exists())

    def test_patient_lists_only_owned_disputes_and_cannot_read_other_detail(self):
        own = self.submit(subject='Own complaint')
        other = User.objects.create_user(email='other@disputes.test')
        foreign = self.submit(actor=other, order_id=self.order(other).pk, subject='Private complaint')
        self.client.force_login(self.patient)
        response = self.client.get('/app/disputes/')
        self.assertContains(response, own.subject)
        self.assertNotContains(response, foreign.subject)
        self.assertEqual(self.client.get(reverse('dispute_detail', args=[foreign.pk])).status_code, 404)

    def test_non_admin_roles_cannot_review_or_read_complaints(self):
        dispute = self.submit()
        for role in ['patient', 'driver', 'pharmacist']:
            self.client.force_login(self.users[role])
            url = reverse('admin_dispute_detail', args=[dispute.pk])
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url, dict(status='resolved', response='Forged', version=0)).status_code, 403)
            with self.assertRaises(PermissionDenied):
                self.review(dispute, actor=self.users[role])
        for role in ['driver', 'pharmacist']:
            self.client.force_login(self.users[role])
            self.assertEqual(self.client.get(reverse('dispute_detail', args=[dispute.pk])).status_code, 404)

    def test_only_one_active_dispute_per_order_service_and_database(self):
        dispute = self.submit()
        with self.assertRaisesMessage(ValidationError, 'active dispute'):
            self.submit(order_id=dispute.order_id)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Dispute.objects.create(order=dispute.order, subject='Duplicate', category='other', description='Duplicate')
        self.assertEqual(Dispute.objects.count(), 1)

    def test_admin_resolves_with_response_notifies_patient_and_preserves_order(self):
        dispute = self.submit()
        order = dispute.order
        self.client.force_login(self.users['admin'])
        self.assertContains(self.client.get('/administrator/disputes/'), dispute.subject)
        response = self.client.post(reverse('admin_dispute_detail', args=[dispute.pk]),
            dict(status='resolved', response='The pharmacy replaced the missing item.', version=0))
        self.assertRedirects(response, reverse('admin_dispute_detail', args=[dispute.pk]))
        dispute.refresh_from_db(); order.refresh_from_db()
        self.assertEqual(dispute.status, 'resolved')
        self.assertIsNotNone(dispute.closed_at)
        self.assertEqual(dispute.history.count(), 2)
        self.assertEqual(dispute.updated_by, self.users['admin'])
        self.assertEqual(order.status, 'pending')
        self.assertFalse(order.cash_collected)
        self.assertTrue(Notification.objects.filter(user=self.patient, kind='dispute').exists())
        self.client.force_login(self.patient)
        self.assertContains(self.client.get(reverse('dispute_detail', args=[dispute.pk])), 'replaced the missing item')

    def test_resolution_and_rejection_need_explanation(self):
        dispute = self.submit()
        for status in ['resolved', 'rejected']:
            with self.assertRaises(ValidationError):
                self.review(dispute, status=status, response='   ')
        self.assertEqual(dispute.history.count(), 1)

    def test_closed_case_reopening_and_state_validation(self):
        dispute = self.review(self.submit(), status='rejected', response='No discrepancy was found.')
        with self.assertRaises(ValidationError):
            self.review(dispute, status='open')
        dispute = self.review(dispute, status='under_review', response='New evidence received.')
        self.assertIsNone(dispute.closed_at)
        self.assertEqual(dispute.history.count(), 3)

    def test_stale_admin_form_cannot_overwrite_a_newer_review(self):
        dispute = self.submit()
        self.review(dispute)
        with self.assertRaisesMessage(ValidationError, 'Another administrator'):
            self.review(dispute, status='resolved', response='Stale decision', version=0)
        dispute.refresh_from_db()
        self.assertEqual(dispute.status, 'under_review')
        self.assertEqual(dispute.history.count(), 2)

    def test_closed_case_cannot_reopen_while_another_case_is_active(self):
        dispute = self.review(self.submit(), status='resolved', response='Fixed.')
        self.submit(order_id=dispute.order_id)
        with self.assertRaisesMessage(ValidationError, 'another active dispute'):
            self.review(dispute)

    def test_evidence_download_is_private_and_generic_media_url_cannot_bypass_it(self):
        evidence = SimpleUploadedFile('evidence.pdf', b'%PDF-1.4\nTest evidence', content_type='application/pdf')
        dispute = self.submit(evidence=evidence)
        url = reverse('dispute_evidence', args=[dispute.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        for role in ['driver', 'pharmacist']:
            self.client.force_login(self.users[role])
            self.assertEqual(self.client.get(url).status_code, 404)
        for role in ['patient', 'admin']:
            self.client.force_login(self.users[role])
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertIn('attachment', response['Content-Disposition'])
            response.close()
        self.client.force_login(self.patient)
        self.assertEqual(self.client.get('/media/' + dispute.evidence.name).status_code, 404)

    def test_invalid_evidence_is_rejected(self):
        for filename, data in [('script.html', b'<script>'), ('fake.pdf', b'not a pdf'), ('fake.png', b'not an image')]:
            with self.assertRaises(ValidationError):
                validate_evidence(SimpleUploadedFile(filename, data))
        with self.assertRaises(ValidationError):
            validate_evidence(SimpleUploadedFile('huge.pdf', b'%PDF-' + b'x' * (10 * 1024 * 1024)))

    def test_patient_and_admin_posts_require_csrf_and_get_never_changes_status(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.patient)
        self.assertEqual(client.post(reverse('dispute_create'), {}).status_code, 403)
        dispute = self.submit()
        client.force_login(self.users['admin'])
        url = reverse('admin_dispute_detail', args=[dispute.pk])
        self.assertEqual(client.post(url, {}).status_code, 403)
        client.get(url, {'status': 'resolved', 'response': 'No mutation'})
        dispute.refresh_from_db(); self.assertEqual(dispute.status, 'open')
        self.assertEqual(resolve(url).func.__module__, 'administration.views')

    def test_filters_and_escaped_content(self):
        dispute = self.review(self.submit(subject='<script>alert(1)</script>'), status='resolved', response='Done')
        self.client.force_login(self.patient)
        self.assertNotContains(self.client.get('/disputes/', {'status': 'open'}), 'alert(1)')
        response = self.client.get('/disputes/', {'q': str(dispute.order_id)})
        self.assertContains(response, '&lt;script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')
