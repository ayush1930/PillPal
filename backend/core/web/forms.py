from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.forms import modelform_factory
from django.contrib.auth.password_validation import validate_password
from django.core.validators import FileExtensionValidator
from django.db import transaction

from core.features.accounts.models import Address, User
from core.features.pharmacies.models import Pharmacy
from core.features.medications.models import Medication
from core.features.inventory.models import InventoryItem, ReorderRequest
from core.features.prescriptions.models import Prescription
from core.features.payments.models import PaymentMethod
from core.features.suppliers.models import Supplier
from core.features.reminders.models import Reminder
from core.features.reviews.models import Review
import json
from datetime import datetime



class SignInForm(AuthenticationForm):
    username = forms.EmailField(label='Email address')


class RegistrationForm(forms.Form):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def clean(self):
        data = super().clean()
        if data.get('password'):
            candidate = User(email=data.get('email', ''), first_name=data.get('first_name', ''), last_name=data.get('last_name', ''))
            try:
                validate_password(data['password'], user=candidate)
            except forms.ValidationError as exc:
                self.add_error('password', exc)
        return data

    def save(self):
        from core.features.accounts.services import register_patient
        return register_patient(**self.cleaned_data)

class ContactForm(forms.Form):
    name = forms.CharField(max_length=150)
    email = forms.EmailField()
    subject = forms.CharField(max_length=200)
    message = forms.CharField(max_length=5000, widget=forms.Textarea)


class MedicationTimesField(forms.CharField):
    def prepare_value(self,value):
        return ', '.join(value) if isinstance(value,list) else value

    def clean(self,value):
        value=super().clean(value)
        if not value: return []
        try:
            times=json.loads(value) if value.startswith('[') else [part.strip() for part in value.split(',')]
            if not isinstance(times,list) or not times: raise ValueError
            for time in times: datetime.strptime(time,'%H:%M')
        except (ValueError,TypeError):
            raise forms.ValidationError('Use times such as 08:00, 20:00.')
        return times

class PrescriptionReviewForm(forms.Form):
    status=forms.ChoiceField(choices=[('approved','Approve'),('rejected','Reject')],label='Decision')
    kind=forms.ChoiceField(choices=Prescription.Kind.choices,label='Prescription type')
    refills_remaining=forms.IntegerField(min_value=0,initial=0)
    review_notes=forms.CharField(required=False,widget=forms.Textarea)


class InvitationForm(forms.Form):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    role = forms.ChoiceField(choices=[(r, r.title()) for r in ['pharmacist','driver','admin']])
    pharmacy = forms.ModelChoiceField(queryset=Pharmacy.objects.filter(active=True), required=False, help_text='Assign a pharmacy when inviting a pharmacist.')

    clean_email = RegistrationForm.clean_email

    def clean(self):
        data = super().clean()
        if data.get('role') == 'pharmacist' and not data.get('pharmacy'):
            self.add_error('pharmacy', 'Choose a pharmacy for this pharmacist.')
        return data

    @transaction.atomic
    def save(self, *, invited_by):
        from core.features.accounts.services import invite_staff
        return invite_staff(actor=invited_by, **self.cleaned_data)

FORMS = {
    'addresses': (Address, ['label','street','city','state','postal_code','latitude','longitude','is_default']),
    'pharmacies': (Pharmacy, ['name','address','phone','email','latitude','longitude','opening_hours','delivery_available','delivery_radius_miles','active']),
    'medications': (Medication, ['name','generic_name','brand','category','dosage_form','description','requires_prescription','active']),
    'inventory': (InventoryItem, ['pharmacy','medication','supplier','price','stock','reorder_level','active']),
    'prescriptions': (Prescription, ['medication_name','doctor_name','issue_date','expiry_date','file']),
    'reminders': (Reminder, ['medication_name','dosage','frequency','times','start_date','end_date','active']),
    'reviews': (Review, ['order','rating','comment']),
    'suppliers': (Supplier, ['name','email','phone','lead_time_days','payment_terms','active']),
    'reorders': (ReorderRequest, ['inventory_item','quantity','priority','notes']),
    'profile': (User, ['first_name','last_name','phone','avatar']),
}

class DomainModelForm(forms.ModelForm):
    def clean(self):
        data = super().clean()
        for start, end in [('issue_date', 'expiry_date'), ('start_date', 'end_date')]:
            if data.get(start) and data.get(end) and data[end] < data[start]:
                self.add_error(end, 'The end date cannot be earlier than the start date.')
        if 'quantity' in data and data['quantity'] < 1:
            self.add_error('quantity', 'Enter a positive quantity.')
        if 'price' in data and data['price'] < 0:
            self.add_error('price', 'Price cannot be negative.')
        if 'latitude' in data and 'longitude' in data:
            if (data['latitude'] is None) != (data['longitude'] is None):
                self.add_error('latitude', 'Enter both latitude and longitude, or leave both blank.')
        return data

    def clean_file(self):
        upload = self.cleaned_data.get('file')
        if upload:
            FileExtensionValidator(['pdf', 'jpg', 'jpeg', 'png', 'webp'])(upload)
            if upload.size > 10 * 1024 * 1024:
                raise forms.ValidationError('Upload a file no larger than 10 MB.')
        return upload


def resource_form(resource, user, data=None, files=None, instance=None):
    model, fields = FORMS[resource]
    widgets = {name: forms.DateInput(attrs={'type':'date'}) for name in fields if name.endswith('_date')}
    form = modelform_factory(model, form=DomainModelForm, fields=fields, widgets=widgets)(data=data, files=files, instance=instance)
    for name in ['latitude', 'longitude']:
        if name in form.fields:
            form.fields[name].help_text = 'Optional saved coordinate for straight-line pharmacy distance estimates.'
    if resource == 'inventory' and user.role == 'pharmacist':
        form.fields['pharmacy'].queryset = Pharmacy.objects.filter(staff__user=user)
    if resource == 'reviews':
        from core.features.orders.models import Order
        from django.db.models import Q
        form.fields['order'].queryset = Order.objects.filter(patient=user, status='delivered').filter(Q(review__isnull=True) | Q(pk=instance.order_id if instance else None))
    if resource == 'reorders' and user.role == 'pharmacist':
        form.fields['inventory_item'].queryset = InventoryItem.objects.filter(pharmacy__staff__user=user)
    if resource == 'reminders':
        form.fields['times']=MedicationTimesField(label='Medication times',widget=forms.TextInput(attrs={'placeholder':'08:00, 20:00'}),help_text='Enter one or more times separated by commas.')
    return form


