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


