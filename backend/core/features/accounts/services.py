from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .models import User


def _email(value):
    email = value.strip().lower()
    from django.core.validators import validate_email
    validate_email(email)
    if User.objects.filter(email__iexact=email).exists():
        raise ValidationError('An account with this email already exists.')
    return email


@transaction.atomic
def register_patient(*, email, password, first_name, last_name):
    email = _email(email)
    candidate = User(email=email, first_name=first_name, last_name=last_name)
    validate_password(password, user=candidate)
    return User.objects.create_user(email=email, password=password, first_name=first_name,
                                    last_name=last_name, role=User.Role.PATIENT)


@transaction.atomic
def invite_staff(*, actor, email, first_name, last_name, role, pharmacy=None):
    from core.features.pharmacies.models import PharmacyStaff
    if not actor.is_authenticated or not actor.is_active or actor.role != 'admin':
        raise PermissionDenied
    if role not in ['pharmacist', 'driver', 'admin']:
        raise ValidationError('Choose a staff role.')
    if role == 'pharmacist' and (pharmacy is None or not pharmacy.active):
        raise ValidationError('Choose an active pharmacy for this pharmacist.')
    user = User.objects.create_user(email=_email(email), first_name=first_name,
        last_name=last_name, role=role, invited_by=actor)
    if role == 'pharmacist':
        PharmacyStaff.objects.create(user=user, pharmacy=pharmacy)
    return user
