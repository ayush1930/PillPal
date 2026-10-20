from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.db.models import Q
from django.core.paginator import Paginator
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from core.web.views import shell
from .forms import DisputeForm
from .models import Dispute
from .services import submit_dispute, visible_disputes


def list_context(request):
    disputes = visible_disputes(request.user)
    status = request.GET.get('status', '')
    search = request.GET.get('q', '').strip()
    tabs = [{'key': '', 'label': 'All', 'count': disputes.count()}]
    tabs += [{'key': key, 'label': label, 'count': disputes.filter(status=key).count()}
             for key, label in Dispute.Status.choices]
    if status in Dispute.Status.values:
        disputes = disputes.filter(status=status)
    if search:
        query = Q(subject__icontains=search) | Q(order__pharmacy__name__icontains=search)
        if search.isdigit():
            query |= Q(order_id=int(search))
        disputes = disputes.filter(query)
    context = shell(request.user, 'disputes')
    context.update(disputes=Paginator(disputes, 20).get_page(request.GET.get('page')),
                   status_filter=status, status_tabs=tabs, search=search)
    return context


@login_required(login_url='auth')
@require_GET
def list_view(request):
    if request.user.role != 'patient':
        raise PermissionDenied
    return render(request, 'disputes/list.html', list_context(request))


@login_required(login_url='auth')
@require_http_methods(['GET', 'POST'])
def create_view(request):
    if request.user.role != 'patient':
        raise PermissionDenied
    form = DisputeForm(request.POST or None, request.FILES or None, actor=request.user,
                       initial={'order': request.GET.get('order')})
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data.copy()
        data['order_id'] = data.pop('order').pk
        try:
            dispute = submit_dispute(actor=request.user, **data)
        except (ValidationError, IntegrityError) as exc:
            form.add_error(None, '; '.join(exc.messages) if isinstance(exc, ValidationError)
                           else 'This order already has an active dispute.')
        else:
            messages.success(request, 'Your dispute has been submitted for administrator review.')
            return redirect('dispute_detail', pk=dispute.pk)
    context = shell(request.user, 'disputes')
    context.update(form=form, form_title='Report an Order Problem', submit_label='Submit Dispute')
    return render(request, 'dashboard/form.html', context)


@login_required(login_url='auth')
@require_GET
def detail_view(request, pk):
    if request.user.role == 'admin':
        return redirect('admin_dispute_detail', pk=pk)
    dispute = get_object_or_404(visible_disputes(request.user), pk=pk)
    context = shell(request.user, 'disputes')
    context.update(dispute=dispute, history=dispute.history.select_related('actor'))
    return render(request, 'disputes/detail.html', context)


@login_required(login_url='auth')
@require_GET
def evidence_view(request, pk):
    dispute = get_object_or_404(visible_disputes(request.user), pk=pk)
    if not dispute.evidence:
        raise Http404
    try:
        return FileResponse(dispute.evidence.open('rb'), as_attachment=True,
                            filename=dispute.evidence.name.rsplit('/', 1)[-1])
    except FileNotFoundError:
        raise Http404
