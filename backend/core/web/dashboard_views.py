from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, F
from django.shortcuts import redirect, render

from core.features.accounts.models import User
from core.features.inventory.models import InventoryItem
from core.features.pharmacies.models import Pharmacy
from core.features.reports.services import order_summary
from .forms import resource_form
from .presentation import pharmacy_context, overview_context, chart_context
from .views import COLUMNS, MODELS, _dashboard_context, display_value, may_edit, scoped

@login_required(login_url='auth')
def pharmacy_search_view(request):
    section = 'pharmacies'
    ctx = _dashboard_context(request, section)
    ctx.update(pharmacy_context(request))
    return render(request,'pharmacies/find.html',ctx)


@login_required(login_url='auth')
def overview_view(request):
    section = 'overview'
    ctx = _dashboard_context(request, section)
    orders = scoped('orders', request.user)
    ctx['stats'] = [('Orders',orders.count()),('Active orders',orders.exclude(status__in=['delivered','cancelled']).count()),('Prescriptions',scoped('prescriptions',request.user).count()),('Unread notifications',ctx['unread_count'])]
    ctx['recent_orders'] = orders.order_by('-created_at')[:6]
    ctx.update(overview_context(request.user,orders,scoped('prescriptions',request.user)))
    ctx.update(chart_context(orders))
    ctx['driver_online'] = request.session.get('driver_online', True)
    return render(request,'dashboard/overview.html',ctx)


@login_required(login_url='auth')
def profile_view(request):
    section = 'profile'
    ctx = _dashboard_context(request, section)
    ctx['form'] = resource_form('profile',request.user,request.POST or None,request.FILES or None,request.user)
    if request.method == 'POST' and ctx['form'].is_valid():
        ctx['form'].save(); messages.success(request,'Profile updated.'); return redirect('dashboard_section',section='profile')
    ctx['pharmacies'] = Pharmacy.objects.filter(staff__user=request.user)
    ctx['addresses'] = scoped('addresses',request.user)
    ctx['payments'] = []
    return render(request,'dashboard/profile.html',ctx)


@login_required(login_url='auth')
def notifications_view(request):
    section = 'notifications'
    ctx = _dashboard_context(request, section)
    ctx['notifications'] = scoped('notifications',request.user).order_by('-created_at')
    if request.GET.get('unread') == '1': ctx['notifications'] = ctx['notifications'].filter(read_at__isnull=True)
    return render(request,'dashboard/notifications.html',ctx)


@login_required(login_url='auth')
def drivers_view(request):
    section = 'drivers'
    ctx = _dashboard_context(request, section)
    ctx['drivers'] = User.objects.filter(role='driver',is_active=True,deliveries__pharmacy__staff__user=request.user).distinct()
    return render(request,'dashboard/drivers.html',ctx)


@login_required(login_url='auth')
def settings_view(request):
    section = 'settings'
    ctx = _dashboard_context(request, section)
    ctx['settings_list'] = [('Email delivery',settings.EMAIL_BACKEND),('Timezone',settings.TIME_ZONE),('Development mode',settings.DEBUG)]
    return render(request,'dashboard/settings.html',ctx)


def _report_response(request, section):
    ctx = _dashboard_context(request, section)
    orders = scoped('orders', request.user)
    delivered = orders.filter(status='delivered')
    ctx['stats'] = order_summary(orders)
    ctx['recent_orders'] = delivered.order_by('-created_at')[:25]
    ctx['is_earnings'] = section == 'earnings'
    ctx.update(chart_context(orders))
    ctx['user_breakdown'] = User.objects.values('role').annotate(total=Count('id')) if request.user.role == 'admin' else []
    return render(request,'dashboard/reports.html',ctx)


@login_required(login_url='auth')
def analytics_view(request):
    return _report_response(request, 'analytics')


@login_required(login_url='auth')
def delivery_charges_view(request):
    return _report_response(request, 'earnings')


def _resource_list_response(request, section):
    ctx = _dashboard_context(request, section)
    aliases = {'queue':'orders','orderhistory':'orders','deliveries':'orders','history':'orders','tracking':'orders','alerts':'inventory'}
    resource = aliases.get(section,section)
    qs = scoped(resource,request.user)
    if section in ['history','orderhistory']: qs = qs.filter(status__in=['delivered','cancelled'])
    if section == 'queue': qs = qs.exclude(status__in=['delivered','cancelled'])
    if section == 'tracking': qs = qs.exclude(status__in=['delivered','cancelled'])
    if section == 'alerts': qs = qs.filter(stock__lte=F('reorder_level'))
    columns = COLUMNS[resource]
    status=request.GET.get('status','')
    status_values=[value for value,_ in MODELS[resource].Status.choices] if hasattr(MODELS[resource],'Status') else []
    if status in status_values: qs=qs.filter(status=status)
    if resource == 'users' and request.GET.get('role') in User.Role.values: qs=qs.filter(role=request.GET['role'])
    if resource == 'inventory' and request.GET.get('category'): qs=qs.filter(medication__category=request.GET['category'])
    search = request.GET.get('q','').strip()
    items = list(qs.order_by('-pk'))
    rows = []
    for item in items:
        values = [display_value(item,field) for _,field in columns]
        if search and search.lower() not in ' '.join(values).lower(): continue
        rows.append({'item':item,'values':values,'editable':may_edit(resource,request.user,item)})
    ctx.update(resource=resource,rows=rows,columns=[label for label,_ in columns],search=search,
               can_create=may_edit(resource,request.user),invite=request.user.role == 'admin' and resource == 'users')
    ctx['status_tabs']=[{'key':'','label':'All','count':scoped(resource,request.user).count()}]+[{'key':value,'label':value.replace('_',' ').title(),'count':scoped(resource,request.user).filter(status=value).count()} for value in status_values]
    ctx['status_filter']=status
    ctx['selected_role']=request.GET.get('role','')
    ctx['categories']=InventoryItem.objects.filter(pk__in=scoped('inventory',request.user).values('pk')).values_list('medication__category',flat=True).distinct() if resource=='inventory' else []
    ctx['selected_category']=request.GET.get('category','')
    ctx['subtitle']={
        'prescriptions':'Upload and manage your prescriptions.' if request.user.role=='patient' else 'Review prescriptions and manage verification decisions.',
        'orders':'View your orders, delivery status, and medication history.',
        'inventory':'Manage pharmacy stock, pricing, and reorder levels.',
        'users':'Manage patients, pharmacists, drivers, and administrators.',
        'reminders':'Stay on top of your medication schedule.', 'reviews':'Your feedback helps improve pharmacy care.',
        'reorders':'Track supplier replenishment requests.', 'pharmacies':'Manage partner pharmacies and their profiles.',
        'suppliers':'Manage your suppliers and contact information.',
    }.get(resource,'Manage your '+resource.replace('-',' ')+'.')
    if resource=='inventory':
        stock=scoped('inventory',request.user)
        ctx['inventory_stats']=[('Total Items',stock.count()),('Low Stock',stock.filter(stock__lte=F('reorder_level')).count()),('Out of Stock',stock.filter(stock=0).count())]
    if resource=='reviews':
        ctx['review_average']=qs.aggregate(value=Avg('rating'))['value']
    template={
        'reminders':'dashboard/reminders.html','reviews':'dashboard/reviews.html',
        'addresses':'dashboard/addresses.html','payments':'dashboard/payments.html',
    }.get(resource,'dashboard/list.html')
    if resource=='prescriptions' and request.user.role=='patient': template='prescriptions/list.html'
    if resource=='orders' and (request.user.role in ['patient','driver'] or section=='queue'): template='orders/list.html'
    if section=='tracking': template='orders/tracking.html'
    if section=='alerts': template='dashboard/alerts.html'
    if section=='history' and request.user.role=='driver': template='orders/history.html'
    return render(request,template,ctx)


@login_required(login_url='auth')
def prescriptions_view(request):
    return _resource_list_response(request, 'prescriptions')


@login_required(login_url='auth')
def orders_view(request):
    return _resource_list_response(request, 'orders')


@login_required(login_url='auth')
def order_queue_view(request):
    return _resource_list_response(request, 'queue')


@login_required(login_url='auth')
def order_history_view(request):
    return _resource_list_response(request, 'orderhistory')


@login_required(login_url='auth')
def deliveries_view(request):
    return _resource_list_response(request, 'deliveries')


@login_required(login_url='auth')
def delivery_history_view(request):
    return _resource_list_response(request, 'history')


@login_required(login_url='auth')
def order_status_view(request):
    return _resource_list_response(request, 'tracking')


@login_required(login_url='auth')
def inventory_view(request):
    return _resource_list_response(request, 'inventory')


@login_required(login_url='auth')
def inventory_alerts_view(request):
    return _resource_list_response(request, 'alerts')


@login_required(login_url='auth')
def users_view(request):
    return _resource_list_response(request, 'users')


@login_required(login_url='auth')
def pharmacies_view(request):
    return _resource_list_response(request, 'pharmacies')


@login_required(login_url='auth')
def medications_view(request):
    return _resource_list_response(request, 'medications')


@login_required(login_url='auth')
def suppliers_view(request):
    return _resource_list_response(request, 'suppliers')


@login_required(login_url='auth')
def reorders_view(request):
    return _resource_list_response(request, 'reorders')


@login_required(login_url='auth')
def reminders_view(request):
    return _resource_list_response(request, 'reminders')


@login_required(login_url='auth')
def reviews_view(request):
    return _resource_list_response(request, 'reviews')


@login_required(login_url='auth')
def addresses_view(request):
    return _resource_list_response(request, 'addresses')

