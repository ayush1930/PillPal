from datetime import datetime

from django.db.models import Avg, Count, F, Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from core.features.accounts.models import Address, User
from core.features.pharmacies.services import distance_km
from core.features.pharmacies.models import Pharmacy
from core.features.inventory.models import InventoryItem
from core.features.medications.models import Medication
from core.features.reminders.models import Reminder
from core.features.reviews.models import Review


def opening_state(pharmacy, at=None):
    """Use saved pharmacy hours, including overnight hours; unknown hours stay unknown."""
    at = at or timezone.localtime()
    schedule = pharmacy.opening_hours or {}
    if isinstance(schedule, str):
        return True if schedule.strip().lower() in ['24/7', '24 hours'] else None
    if not isinstance(schedule, dict): return None
    if schedule.get('always_open') is True: return True
    day = at.strftime('%A').lower()
    entry = schedule.get(day, schedule.get(day[:3], schedule.get(at.strftime('%A'), schedule.get('daily'))))
    if entry is None: return None
    if entry is False or (isinstance(entry,str) and entry.lower() == 'closed'): return False
    if isinstance(entry,str):
        if entry.lower() in ['24/7','24 hours','open']: return True
        entry = entry.replace('–','-').split('-')
        if len(entry) != 2: return None
        entry = {'open':entry[0].strip(),'close':entry[1].strip()}
    if not isinstance(entry,dict): return None
    if entry.get('closed'): return False
    try:
        opening = datetime.strptime(entry['open'],'%H:%M').time()
        closing = datetime.strptime(entry['close'],'%H:%M').time()
    except (KeyError,ValueError,TypeError): return None
    now = at.time().replace(tzinfo=None)
    if opening == closing: return True
    if opening > closing: return now >= opening or now < closing
    return opening <= now < closing


def pharmacy_context(request):
    search = request.GET.get('q','').strip()
    med = request.GET.get('med','').strip()
    sort = request.GET.get('sort','rating')
    rating = request.GET.get('rating','')
    delivery = request.GET.get('delivery') == '1'
    open_only = request.GET.get('open') == '1'
    qs = Pharmacy.objects.filter(active=True).annotate(rating=Avg('reviews__rating'),review_count=Count('reviews',distinct=True))
    if search: qs = qs.filter(Q(name__icontains=search) | Q(address__icontains=search))
    if delivery: qs = qs.filter(delivery_available=True)
    if rating in ['4','4.5']: qs = qs.filter(rating__gte=float(rating))
    address = Address.objects.filter(user=request.user).order_by('-is_default', 'pk').first()
    pharmacies = list(qs)
    for pharmacy in pharmacies:
        pharmacy.open_now = opening_state(pharmacy)
        pharmacy.distance = distance_km(pharmacy, address)
    if open_only: pharmacies = [p for p in pharmacies if p.open_now is True]
    if sort == 'name': pharmacies.sort(key=lambda p:p.name.casefold())
    elif sort == 'distance': pharmacies.sort(key=lambda p:(p.distance is None, p.distance or 0, p.name))
    else: pharmacies.sort(key=lambda p: (-(p.rating or 0),p.name))
    results = InventoryItem.objects.none()
    if len(med) >= 2:
        results = InventoryItem.objects.filter(active=True,stock__gt=0,pharmacy__active=True,medication__active=True).filter(Q(medication__name__icontains=med) | Q(medication__generic_name__icontains=med)).select_related('medication','pharmacy').order_by('price','pk')[:30]
    return {'pharmacies':pharmacies,'med_results':results,'search':search,'med_search':med,'sort':sort,
            'rating_filter':rating,'delivery_filter':delivery,'open_filter':open_only,
            'has_filters': bool(rating or delivery or open_only),'page_title':'Find Pharmacy',
            'subtitle':'Browse partner pharmacies or search for a specific medication.'}


def overview_context(user,orders,prescriptions):
    today = timezone.localdate()
    recent = orders.select_related('pharmacy','patient','driver').prefetch_related('items__inventory_item__medication').order_by('-created_at')[:4]
    reminders = Reminder.objects.filter(patient=user,active=True,start_date__lte=today).filter(Q(end_date__isnull=True)|Q(end_date__gte=today))
    if user.role == 'patient':
        stats = [dict(label='Active Prescriptions',value=prescriptions.filter(status='approved',voided_at__isnull=True).count(),sub='Verified',icon='FileText'),dict(label='Total Orders',value=orders.count(),sub='All time',icon='Package'),dict(label='Active Reminders',value=reminders.count(),sub='Medications',icon='Bell'),dict(label='Avg Rating Given',value=Review.objects.filter(patient=user).aggregate(avg=Avg('rating'))['avg'] or '—',sub='Your reviews',icon='Star')]
        title=f'Good {"morning" if timezone.localtime().hour < 12 else "afternoon" if timezone.localtime().hour < 18 else "evening"}, {user.first_name or "there"}'
        subtitle='Here is what is happening with your medications today.'
    elif user.role == 'pharmacist':
        inventory = InventoryItem.objects.filter(pharmacy__staff__user=user,active=True)
        stats=[dict(label='Pending Orders',value=orders.filter(status='pending').count(),sub='Awaiting acceptance',icon='Clipboard'),dict(label='Processing',value=orders.filter(status='processing').count(),sub='Being prepared',icon='Package'),dict(label='Pending Prescriptions',value=prescriptions.filter(status='pending').count(),sub='Need verification',icon='FileText'),dict(label='Low Stock Items',value=inventory.filter(stock__lte=F('reorder_level')).count(),sub='Require attention',icon='AlertTriangle')]
        title='Pharmacy Dashboard'; subtitle='Manage orders, verify prescriptions, and keep your pharmacy stocked.'
    elif user.role == 'driver':
        assigned=orders.filter(driver=user)
        stats=[dict(label='Assigned Today',value=assigned.filter(created_at__date=today).count(),sub='Your deliveries',icon='Truck'),dict(label='Completed Today',value=assigned.filter(delivered_at__date=today).count(),sub='Delivered',icon='CheckCircle'),dict(label='Active Deliveries',value=assigned.filter(status='out_for_delivery').count(),sub='In transit',icon='Navigation'),dict(label='Rating',value=Review.objects.filter(driver=user).aggregate(avg=Avg('rating'))['avg'] or '—',sub='Patient feedback',icon='Star')]
        title='Driver Dashboard'; subtitle=f'Welcome back, {user.first_name or "driver"}.'
    else:
        stats=[dict(label='Total Users',value=User.objects.count(),sub=f'{User.objects.filter(role="patient",is_active=True).count()} active patients',icon='Users'),dict(label='Orders Today',value=orders.filter(created_at__date=today).count(),sub='Across all pharmacies',icon='Package'),dict(label='Monthly Order Value',value=orders.filter(created_at__year=today.year,created_at__month=today.month).exclude(status='cancelled').aggregate(value=Sum('total'))['value'] or 0,sub='Order totals',icon='BarChart2',money=True),dict(label='Satisfaction',value=Review.objects.aggregate(avg=Avg('rating'))['avg'] or '—',sub='Average rating',icon='Star')]
        title='Admin Overview'; subtitle='Monitor your platform, pharmacies, and patient activity.'
    pending=list(prescriptions.filter(status='pending').select_related('patient').order_by('created_at')[:5])
    breakdown=[dict(label=status.replace('_',' ').title(),value=orders.filter(status=status).count(),key=status) for status in ['pending','processing','ready','out_for_delivery','delivered','cancelled']]
    for item in breakdown: item['percent']=round(item['value']/max(orders.count(),1)*100)
    return {'summary_stats':stats,'overview_title':title,'subtitle':subtitle,'recent_orders':recent,'today_reminders':reminders,
            'active_order':orders.filter(status='out_for_delivery',patient=user).first(),
            'pending_prescriptions':pending,'available_deliveries':orders.filter(status='ready',driver__isnull=True,delivery_type='delivery')[:5],
            'order_breakdown':breakdown,'order_total_count':orders.count()}


def chart_context(orders):
    months=list(orders.exclude(status='cancelled').annotate(month=TruncMonth('created_at')).values('month').annotate(count=Count('id'),total=Sum('total')).order_by('month'))[-6:]
    max_count=max([m['count'] for m in months] or [1])
    max_value=max([m['total'] for m in months] or [1])
    for month in months:
        month['height']=round(month['count']/max_count*100) if max_count else 0
        month['revenue_height']=round(month['total']/max_value*100) if max_value else 0
    return {'chart_months':months}
