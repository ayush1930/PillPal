from django import forms
from core.features.orders.models import Order
from .models import Dispute
from .services import validate_evidence

class DisputeForm(forms.Form): # allow patient to submit commplaint
    order = forms.ModelChoiceField(queryset=Order.objects.none())
    subject = forms.CharField(max_length=180)
    category = forms.ChoiceField(choices=Dispute.Category.choices)
    description = forms.CharField(max_length=4000, widget=forms.Textarea,
        help_text='Describe what happened and the outcome you are requesting.')
    evidence = forms.FileField(required=False,
        help_text='Optional PDF, JPG, PNG or WebP, up to 10 MB.')

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['order'].queryset = Order.objects.filter(patient=actor).order_by('-created_at')
        self.fields['order'].label_from_instance = lambda order: f'Order #{order.pk} — {order.pharmacy.name}'

    def clean_evidence(self):
        return validate_evidence(self.cleaned_data.get('evidence'))

class DisputeReviewForm(forms.Form):
    status = forms.ChoiceField(choices=Dispute.Status.choices)
    response = forms.CharField(max_length=4000, required=False, widget=forms.Textarea,
                               label='Response to patient')
    version = forms.IntegerField(min_value=0, widget=forms.HiddenInput)

    def clean(self):
        data = super().clean()
        if data.get('status') in ['resolved', 'rejected'] and not data.get('response', '').strip():
            self.add_error('response', 'Explain the resolution or rejection before closing the dispute.')
        return data