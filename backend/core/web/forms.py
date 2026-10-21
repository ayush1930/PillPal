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