from django import forms
from core.models import Pharmacy, Supplier, Medication


class InventoryIntakeForm(forms.Form):
    medication = forms.ModelChoiceField(queryset=Medication.objects.filter(active=True), required=False, label='Existing medication', help_text='Choose a catalogue item, or leave blank and enter the new medication details below.')
    name = forms.CharField(max_length=180, required=False)
    generic_name = forms.CharField(max_length=180, required=False)
    brand = forms.CharField(max_length=180, required=False)
    category = forms.CharField(max_length=120, required=False)
    dosage_form = forms.CharField(max_length=80, required=False)
    requires_prescription = forms.BooleanField(required=False)
    pharmacy = forms.ModelChoiceField(queryset=Pharmacy.objects.none())
    supplier = forms.ModelChoiceField(queryset=Supplier.objects.filter(active=True), required=False)
    price = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    quantity = forms.IntegerField(min_value=1, label='Quantity to add')
    reorder_level = forms.IntegerField(min_value=0, initial=5)

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        pharmacies = Pharmacy.objects.filter(active=True)
        if actor.role != 'admin':
            pharmacies = pharmacies.filter(staff__user=actor)
        self.fields['pharmacy'].queryset = pharmacies.distinct()

    def clean(self):
        data = super().clean()
        if not data.get('medication'):
            for field in ['name', 'generic_name', 'category']:
                if not data.get(field):
                    self.add_error(field, 'Enter this detail for a new medication, or select an existing medication.')
        return data
