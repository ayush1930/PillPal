from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.shortcuts import redirect, render

from core.web.views import shell
from .forms import InventoryIntakeForm
from .services import add_inventory


@login_required(login_url='auth')
def inventory_intake_view(request):
    if request.user.role not in ['admin', 'pharmacist']:
        raise PermissionDenied
    form = InventoryIntakeForm(request.POST or None, actor=request.user, initial={'quantity': 1})
    if request.method == 'POST' and form.is_valid():
        try:
            add_inventory(actor=request.user, **form.cleaned_data)
        except (ValidationError, IntegrityError) as exc:
            form.add_error(None, '; '.join(exc.messages) if isinstance(exc, ValidationError) else 'This stock record changed. Reload the page and try again.')
        else:
            messages.success(request, 'Medication stock saved.')
            return redirect('dashboard_section', section='inventory')
    context = shell(request.user, 'inventory')
    context.update(form=form)
    return render(request, 'inventory/intake.html', context)
