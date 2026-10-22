from datetime import timedelta
from decimal import Decimal
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import resolve, reverse
from django.utils import timezone

from core.features.accounts.models import User, Address
from core.features.pharmacies.models import Pharmacy, PharmacyStaff
from core.features.medications.models import Medication
from core.features.inventory.models import InventoryItem
from core.features.prescriptions.models import Prescription
from core.features.orders.models import Order, OrderItem
from .views import NAV


class NativeWebsiteTests(TestCase):
    def setUp(self):
        self.temp_media = TemporaryDirectory()
        self.addCleanup(self.temp_media.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=self.temp_media.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.users = {role: User.objects.create_user(email=f'{role}@example.com',password='PillPal-Test-Password-26!',role=role,first_name=role.title()) for role in NAV}
        self.patient = self.users['patient']
        self.pharmacy = Pharmacy.objects.create(name='Test Pharmacy',address='1 Test Street',phone='123')
        PharmacyStaff.objects.create(pharmacy=self.pharmacy,user=self.users['pharmacist'])
        self.medication = Medication.objects.create(name='Test medication',generic_name='Test',category='General',requires_prescription=True)
        self.stock = InventoryItem.objects.create(pharmacy=self.pharmacy,medication=self.medication,price=Decimal('10.00'),stock=10)
        self.address = Address.objects.create(user=self.patient,label='Home',street='1 Main',city='Test',state='Test',postal_code='123')
        self.rx = Prescription.objects.create(patient=self.patient,medication_name='Test medication',doctor_name='Dr Test',issue_date=timezone.localdate(),expiry_date=timezone.localdate()+timedelta(days=30),file=SimpleUploadedFile('rx.pdf',b'prescription'),status='approved',kind='single_use')

    def test_public_pages_are_native_html(self):
        for url in ['/', '/auth', '/auth?mode=register','/password-reset/']:
            response = self.client.get(url)
            self.assertEqual(response.status_code,200)
            self.assertContains(response,'/static/css/pillpal.css')
            self.assertNotContains(response,'id="root"')

    def test_all_role_dashboard_sections_render(self):
        for role,user in self.users.items():
            self.client.force_login(user)
            for key,_ in NAV[role]:
                with self.subTest(role=role,section=key):
                    response = self.client.get(reverse('dashboard_section',args=[key]))
                    self.assertEqual(response.status_code,200)
            self.client.logout()

    def test_registration_creates_only_patient_then_logs_in(self):
        response = self.client.post('/auth?mode=register',{'email':'new@example.com','first_name':'New','last_name':'Patient','password':'PillPal-New-Password-26!','role':'admin'})
        self.assertRedirects(response,reverse('dashboard'))
        self.assertEqual(User.objects.get(email='new@example.com').role,'patient')

    def test_login_and_logout(self):
        response = self.client.post('/auth',{'username':self.patient.email,'password':'PillPal-Test-Password-26!'})
        self.assertRedirects(response,reverse('dashboard'))
        self.assertRedirects(self.client.post(reverse('sign_out')),reverse('home'))

    def test_form_post_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.patient)
        response = client.post(reverse('resource_create',args=['reminders']),{})
        self.assertEqual(response.status_code,403)

    def test_checkout_decrements_stock_and_delivery_voids_prescription(self):
        self.client.force_login(self.patient)
        self.client.post(reverse('cart_update',args=[self.stock.pk]),{'quantity':'2'})
        response = self.client.post(reverse('cart'),{'delivery_type':'delivery','address':self.address.pk,'prescription':self.rx.pk})
        order = Order.objects.get(patient=self.patient)
        self.assertRedirects(response,reverse('order_detail',args=[order.pk]))
        self.assertEqual(order.total,Decimal('24.99'))
        self.stock.refresh_from_db(); self.assertEqual(self.stock.stock,8)
        self.client.force_login(self.users['pharmacist'])
        for status in ['processing','ready']:
            response = self.client.post(reverse('resource_action',args=['orders',order.pk,'status']),{'status':status})
            self.assertEqual(response.status_code,302)
        self.client.force_login(self.users['driver'])
        self.client.post(reverse('resource_action',args=['orders',order.pk,'accept']))
        self.client.post(reverse('resource_action',args=['orders',order.pk,'deliver']))
        order.refresh_from_db(); self.rx.refresh_from_db()
        self.assertEqual(order.status,'delivered')
        self.assertIsNotNone(self.rx.voided_at)

    def test_checkout_requires_prescription_and_owned_address(self):
        self.client.force_login(self.patient)
        self.client.post(reverse('cart_update',args=[self.stock.pk]),{'quantity':1})
        response = self.client.post(reverse('cart'),{'delivery_type':'delivery','address':self.address.pk})
        self.assertContains(response,'A prescription is required')
        self.assertFalse(Order.objects.exists())
        other = User.objects.create_user(email='other@example.com',password='TestPassword-26!')
        foreign = Address.objects.create(user=other,label='Home',street='Other street',city='Other',state='Other',postal_code='456')
        response = self.client.post(reverse('cart'),{'delivery_type':'delivery','address':foreign.pk,'prescription':self.rx.pk})
        self.assertEqual(response.status_code,404)
        self.assertFalse(Order.objects.exists())

    def test_oversold_checkout_rolls_back(self):
        self.client.force_login(self.patient)
        self.client.post(reverse('cart_update',args=[self.stock.pk]),{'quantity':2})
        self.stock.stock = 1; self.stock.save()
        response = self.client.post(reverse('cart'),{'delivery_type':'pickup','prescription':self.rx.pk})
        self.assertContains(response,'Insufficient stock')
        self.assertFalse(Order.objects.exists())

    def test_patient_cannot_read_other_patients_orders(self):
        other = User.objects.create_user(email='other@example.com',password='TestPassword-26!')
        order = Order.objects.create(patient=other,pharmacy=self.pharmacy,delivery_type='pickup',subtotal=10,total=10)
        self.client.force_login(self.patient)
        self.assertEqual(self.client.get(reverse('order_detail',args=[order.pk])).status_code,404)

    def test_staff_invitation_assigns_pharmacy(self):
        self.client.force_login(self.users['admin'])
        response = self.client.post(reverse('invite_staff'),{'first_name':'New','last_name':'Staff','email':'staff@example.com','role':'pharmacist','pharmacy':self.pharmacy.pk})
        self.assertEqual(response.status_code,302)
        staff = User.objects.get(email='staff@example.com')
        self.assertFalse(staff.has_usable_password())
        self.assertTrue(PharmacyStaff.objects.filter(user=staff,pharmacy=self.pharmacy).exists())

    def test_patient_cannot_access_staff_forms(self):
        self.client.force_login(self.patient)
        for url in [reverse('invite_staff'),reverse('resource_create',args=['inventory']),reverse('export_orders')]:
            self.assertEqual(self.client.get(url).status_code,403)

    def test_pharmacist_cannot_edit_another_pharmacys_stock(self):
        other = Pharmacy.objects.create(name='Other',address='Other',phone='123')
        stock = InventoryItem.objects.create(pharmacy=other,medication=self.medication,price=5,stock=5)
        self.client.force_login(self.users['pharmacist'])
        self.assertEqual(self.client.get(reverse('resource_edit',args=['inventory',stock.pk])).status_code,404)

    def test_prescription_upload_and_reminder_save(self):
        self.client.force_login(self.patient)
        response = self.client.post(reverse('resource_create',args=['prescriptions']),{'medication_name':'New','doctor_name':'Dr Test','issue_date':str(timezone.localdate()),'expiry_date':str(timezone.localdate()+timedelta(days=30)),'file':SimpleUploadedFile('new.pdf',b'new prescription')})
        self.assertEqual(response.status_code,302)
        self.assertEqual(Prescription.objects.get(medication_name='New').patient,self.patient)
        response = self.client.post(reverse('resource_create',args=['reminders']),{'medication_name':'New','dosage':'1 tablet','frequency':'Daily','times':'["08:00"]','start_date':str(timezone.localdate()),'active':'on'})
        self.assertEqual(response.status_code,302)

    def test_semester_one_has_no_api_routes(self):
        for url in ['/api/auth/register/', '/api/orders/', '/api/inventory/']:
            self.assertEqual(self.client.get(url).status_code, 404)

    def test_original_svg_library_and_page_icons(self):
        from pathlib import Path
        from xml.etree import ElementTree
        from core.templatetags.pillpal_icons import ICONS, icon, nav_icon
        from django.conf import settings
        for name in ICONS:
            with self.subTest(icon=name):
                markup = str(icon(name))
                ElementTree.fromstring(markup)
                self.assertTrue((settings.BASE_DIR.parent / 'frontend/static/icons' / f'{name}.svg').is_file())
                self.assertIn('aria-hidden="true"', markup)
        self.assertIn('M16 10 H26', str(icon('Logo')))
        self.assertEqual(str(nav_icon('profile','pharmacist')),str(icon('Building',16)))
        response = self.client.get('/')
        self.assertContains(response, 'How PillPal works')
        self.assertContains(response, 'Receive delivery')
        self.assertContains(response, '/static/images/pillpal-hero.jpeg')
        self.assertNotContains(response, '<span class="feature-icon">✚')
        self.assertContains(response, 'id="about"')
        self.assertContains(response, 'id="testimonials"')
        self.assertContains(response, 'id="contact"')
        self.assertNotContains(self.client.get('/auth'), '<img')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_native_contact_form(self):
        from django.core import mail
        response = self.client.post('/contact/',{'name':'Test','email':'test@example.com','subject':'Question','message':'Please help with an order.'})
        self.assertRedirects(response, '/#contact')
        self.assertEqual(len(mail.outbox),1)
        self.client.post('/contact/',{'email':'invalid'})
        self.assertEqual(len(mail.outbox),1)
