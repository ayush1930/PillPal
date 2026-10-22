from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.core.mail import send_mail
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.views.decorators.http import require_GET, require_http_methods

from core.web.forms import InvitationForm
from core.web.views import shell, scoped, render_dashboard

@login_required(login_url="auth")
def dashboard_view(request, section="overview"):
    if request.user.role != "admin": raise PermissionDenied
    if section == 'disputes':
        return disputes_view(request)
    return render_dashboard(request, section)


@login_required(login_url='auth')
@require_GET
def disputes_view(request):
    if request.user.role != 'admin':
        raise PermissionDenied
    from core.features.disputes.views import list_context
    return render(request, 'disputes/list.html', list_context(request))


@login_required(login_url='auth')
@require_http_methods(['GET', 'POST'])
def dispute_review_view(request, pk):
    if request.user.role != 'admin':
        raise PermissionDenied
    from core.features.disputes.forms import DisputeReviewForm
    from core.features.disputes.services import review_dispute, visible_disputes
    dispute = get_object_or_404(visible_disputes(request.user), pk=pk)
    form = DisputeReviewForm(request.POST or None, initial={
        'status': dispute.status, 'response': dispute.admin_response, 'version': dispute.version})
    if request.method == 'POST' and form.is_valid():
        try:
            review_dispute(actor=request.user, dispute_id=pk, **form.cleaned_data)
        except (ValidationError, IntegrityError) as exc:
            form.add_error(None, '; '.join(exc.messages) if isinstance(exc, ValidationError)
                           else 'This order already has an active dispute. Reload before reopening it.')
        else:
            messages.success(request, 'Dispute updated. The patient has been notified.')
            return redirect('admin_dispute_detail', pk=pk)
    context = shell(request.user, 'disputes')
    context.update(dispute=dispute, history=dispute.history.select_related('actor'), form=form)
    return render(request, 'disputes/detail.html', context)

@login_required(login_url='auth')
def staff_invitation_view(request):
    if request.user.role != 'admin': raise PermissionDenied
    form = InvitationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save(invited_by=request.user)
        uid = urlsafe_base64_encode(force_bytes(user.pk)); token = default_token_generator.make_token(user)
        url = request.build_absolute_uri(reverse('password_reset_confirm',kwargs={'uidb64':uid,'token':token}))
        send_mail('Your PillPal staff invitation',f'Set your password: {url}',settings.DEFAULT_FROM_EMAIL,[user.email])
        messages.success(request,'Staff account created. The invitation was sent through the configured email backend.')
        return redirect('dashboard_section',section='users')
    ctx = shell(request.user,'users'); ctx.update(form=form,resource='staff invitation',form_title='Invite Staff Member',submit_label='Send Invitation')
    return render(request,'dashboard/form.html',ctx)


@login_required(login_url='auth')
def order_export_view(request):
    import csv
    if request.user.role != 'admin': raise PermissionDenied
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="pillpal-orders.csv"'
    writer = csv.writer(response); writer.writerow(['Order','Patient','Pharmacy','Status','Total'])
    for order in scoped('orders',request.user):
        # Prevent spreadsheet applications from interpreting user-supplied text as formulas.
        values = [str(order.pk),order.patient.name,order.pharmacy.name,order.status,str(order.total)]
        writer.writerow(["'" + v if v.startswith(('=','+','-','@')) else v for v in values])
    return response

