from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.features.accounts.models import User, Address
from core.features.pharmacies.models import Pharmacy
from core.features.medications.models import Medication
from core.features.inventory.models import InventoryItem
from core.features.prescriptions.models import Prescription
from core.features.orders.models import Order
from core.features.reviews.models import Review
from core.features.notifications.models import Notification
from core.features.orders.services import place_order, accept_delivery, complete_order, change_order_status
from core.features.inventory.services import change_reorder_status
from .forms import SignInForm, RegistrationForm, FORMS, resource_form
from .forms import ContactForm, PrescriptionReviewForm
from .presentation import opening_state


NAV = {
    'patient': [('overview','Overview'),('prescriptions','Prescriptions'),('orders','My Orders'),('tracking','Order Status'),('pharmacies','Find Pharmacy'),('reminders','Reminders'),('reviews','My Reviews'),('disputes','My Disputes'),('notifications','Notifications'),('profile','Profile')],
    'pharmacist': [('overview','Overview'),('queue','Order Queue'),('prescriptions','Prescriptions'),('inventory','Inventory'),('alerts','Alerts'),('reorders','Reorders'),('orderhistory','Order History'),('drivers','Drivers'),('reviews','Reviews'),('notifications','Notifications'),('profile','Pharmacy Profile')],
    'driver': [('overview','Overview'),('deliveries','My Deliveries'),('history','History'),('earnings','Delivery Charges'),('notifications','Notifications'),('profile','Profile')],
    'admin': [('overview','Overview'),('users','User Management'),('orders','All Orders'),('disputes','Disputes'),('pharmacies','Pharmacies'),('prescriptions','Prescriptions'),('inventory','Inventory'),('suppliers','Suppliers'),('reorders','Reorders'),('analytics','Analytics'),('reviews','Reviews'),('notifications','Notifications'),('settings','System Settings'),('profile','Profile')],
}
MODELS = {name: pair[0] for name, pair in FORMS.items()}
MODELS.update(orders=Order, notifications=Notification, users=User)


def scoped(resource, user):
    if resource not in MODELS:
        raise Http404
    qs = MODELS[resource].objects.all()
    role = user.role
    if resource == 'profile': return qs.filter(pk=user.pk)
    if resource in ['addresses','payments','notifications']: return qs.filter(user=user)
    if resource == 'reminders': return qs.filter(patient=user)
    if resource == 'users': return qs if role == 'admin' else qs.none()
    if resource in ['pharmacies','medications']: return qs if role in ['admin','pharmacist'] else qs.filter(active=True)
    if resource == 'inventory':
        if role == 'pharmacist': return qs.filter(pharmacy__staff__user=user)
        return qs if role == 'admin' else qs.filter(active=True, pharmacy__active=True, medication__active=True)
    if resource == 'prescriptions':
        qs = qs.filter(deleted_at__isnull=True)
        if role == 'patient': return qs.filter(patient=user)
        if role == 'pharmacist': return qs.filter(Q(orders__pharmacy__staff__user=user) | Q(status='pending')).distinct()
        return qs if role == 'admin' else qs.none()
    if resource == 'orders':
        if role == 'patient': return qs.filter(patient=user)
        if role == 'driver': return qs.filter(Q(driver=user) | Q(status='ready',driver__isnull=True,delivery_type='delivery'))
        if role == 'pharmacist': return qs.filter(pharmacy__staff__user=user).distinct()
        return qs
    if resource == 'reviews':
        if role == 'patient': return qs.filter(patient=user)
        if role == 'pharmacist': return qs.filter(pharmacy__staff__user=user)
        if role == 'driver': return qs.filter(driver=user)
        return qs
    if resource == 'suppliers': return qs if role in ['admin','pharmacist'] else qs.none()
    if resource == 'reorders':
        if role == 'pharmacist': return qs.filter(inventory_item__pharmacy__staff__user=user)
        return qs if role == 'admin' else qs.none()
    return qs.none()


def may_edit(resource, user, item=None):
    if resource == 'profile': return item is None or item.pk == user.pk
    if resource in ['addresses','payments','reminders','reviews']: return user.role == 'patient'
    if resource == 'prescriptions': return user.role == 'patient' and (item is None or item.status == 'pending')
    if resource in ['pharmacies','medications']: return user.role == 'admin' or (user.role == 'pharmacist' and resource == 'pharmacies' and item and item.staff.filter(user=user).exists())
    if resource in ['inventory','suppliers','reorders']: return user.role in ['admin','pharmacist']
    return False


def shell(user, section):
    return {'nav': [{'key': key, 'label': label} for key,label in NAV[user.role]], 'section': section,
            'page_title': dict(NAV[user.role]).get(section, section.replace('_',' ').title()),
            'unread_count': Notification.objects.filter(user=user,read_at__isnull=True).count()}


def home_view(request):
    return render(request, 'landing.html', {
        'pharmacy_count': Pharmacy.objects.filter(active=True).count(),
        'medication_count': Medication.objects.filter(active=True).count(),
        'delivered_count': Order.objects.filter(status='delivered').count(),
        'review_count': Review.objects.count(),
        'rated_pharmacies': Pharmacy.objects.filter(active=True).annotate(
            rating=Avg('reviews__rating'), review_count=Count('reviews')
        ).filter(review_count__gt=0).order_by('-rating')[:3],
    })


@require_POST
def contact_view(request):
    form = ContactForm(request.POST)
    if form.is_valid():
        data = form.cleaned_data
        # The console email backend is the local development default.
        send_mail(
            f"PillPal contact: {data['subject']}",
            f"From: {data['name']} <{data['email']}>\n\n{data['message']}",
            settings.DEFAULT_FROM_EMAIL, [settings.DEFAULT_FROM_EMAIL],
        )
        messages.success(request, 'Your message has been submitted.')
    else:
        messages.error(request, 'Please enter a name, valid email, subject and message.')
    return redirect(reverse('home') + '#contact')


def authentication_view(request):
    """Keep the existing /auth and /auth?mode=register addresses working."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.GET.get('reset'):
        parts = request.GET['reset'].split(':', 1)
        if len(parts) == 2:
            return redirect('password_reset_confirm', uidb64=parts[0], token=parts[1])
    if request.GET.get('mode') == 'register':
        return register_view(request)
    return login_view(request)


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = SignInForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.get_user())
        return redirect('dashboard')
    return render(request, 'accounts/auth.html', {'form': form, 'mode': 'signin'})


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = RegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        return redirect('dashboard')
    return render(request, 'accounts/auth.html', {'form': form, 'mode': 'register'})


@require_POST
def logout_view(request):
    logout(request)
    return redirect('home')


@login_required(login_url='auth')
def prescription_file_view(request,pk):
    prescription=get_object_or_404(scoped('prescriptions',request.user),pk=pk)
    if not prescription.file: raise Http404
    try: file=prescription.file.open('rb')
    except FileNotFoundError: raise Http404
    return FileResponse(file,as_attachment=False,filename=prescription.file.name.rsplit('/',1)[-1])


@login_required(login_url='auth')
def media_file_view(request, path):
    """Never expose uploaded prescriptions through an unrestricted media directory."""
    prescription = scoped('prescriptions', request.user).filter(file=path).first()
    order = scoped('orders', request.user).filter(proof_of_delivery=path).first()
    avatar = User.objects.filter(pk=request.user.pk, avatar=path).first()
    field = prescription.file if prescription else order.proof_of_delivery if order else avatar.avatar if avatar else None
    if not field:
        raise Http404
    try:
        return FileResponse(field.open('rb'), filename=field.name.rsplit('/', 1)[-1])
    except FileNotFoundError:
        raise Http404


@login_required(login_url='auth')
@require_POST
def notifications_read_all_view(request):
    scoped('notifications',request.user).filter(read_at__isnull=True).update(read_at=timezone.now())
    return redirect('dashboard_section',section='notifications')


@login_required(login_url='auth')
@require_POST
def driver_availability_view(request):
    if request.user.role != 'driver':
        raise PermissionDenied
    request.session['driver_online'] = not request.session.get('driver_online', True)
    return redirect('dashboard')




@login_required(login_url='auth')
def prescription_review_view(request,pk):
    if request.user.role not in ['pharmacist','admin']: raise PermissionDenied
    prescription=get_object_or_404(scoped('prescriptions',request.user),pk=pk)
    form=PrescriptionReviewForm(request.POST or None,initial={'status':'approved','kind':prescription.kind or 'single_use','refills_remaining':prescription.refills_remaining,'review_notes':prescription.review_notes})
    if request.method == 'POST' and form.is_valid():
        data=form.cleaned_data
        prescription.status=data['status']; prescription.reviewed_by=request.user; prescription.review_notes=data['review_notes']
        if data['status']=='approved': prescription.kind=data['kind']; prescription.refills_remaining=data['refills_remaining']
        prescription.save()
        url=reverse('dashboard_section',kwargs={'section':'prescriptions'})
        return redirect(url)
    ctx=shell(request.user,'prescriptions'); ctx.update(form=form,form_title='Review Prescription',resource='prescriptions',is_edit=True,submit_label='Save Review',reviewed_prescription=prescription)
    return render(request,'dashboard/form.html',ctx)


def display_value(item, field):
    value = item
    for part in field.split('.'):
        value = getattr(value, part, None)
        if value is None: return '—'
    if hasattr(value, 'name'): return value.name
    if hasattr(value, 'medication_name'): return value.medication_name
    return str(value) if value not in [None,''] else '—'


COLUMNS = {
    'prescriptions':[('Medication','medication_name'),('Patient','patient.name'),('Doctor','doctor_name'),('Status','status'),('Expires','expiry_date')],
    'orders':[('Order','id'),('Patient','patient.name'),('Pharmacy','pharmacy.name'),('Status','status'),('Total','total')],
    'pharmacies':[('Pharmacy','name'),('Address','address'),('Phone','phone'),('Delivery','delivery_available')],
    'medications':[('Medication','name'),('Generic name','generic_name'),('Category','category'),('Prescription','requires_prescription')],
    'inventory':[('Medication','medication.name'),('Pharmacy','pharmacy.name'),('Price','price'),('Stock','stock'),('Reorder level','reorder_level')],
    'reorders':[('Medication','inventory_item.medication.name'),('Quantity','quantity'),('Priority','priority'),('Status','status')],
    'suppliers':[('Supplier','name'),('Email','email'),('Phone','phone'),('Lead time','lead_time_days'),('Terms','payment_terms')],
    'reminders':[('Medication','medication_name'),('Dosage','dosage'),('Frequency','frequency'),('Times','times'),('Active','active')],
    'reviews':[('Pharmacy','pharmacy.name'),('Rating','rating'),('Comment','comment')],
    'users':[('Name','name'),('Email','email'),('Role','role'),('Active','is_active')],
    'addresses':[('Label','label'),('Street','street'),('City','city'),('Default','is_default')],
    'payments':[('Type','kind'),('Provider','provider'),('Display','display_value'),('Default','is_default')],
}


@login_required(login_url='auth')
def dashboard_view(request, section='overview'):
    if request.user.role == 'admin':
        from administration.views import dashboard_view as admin_dashboard
        return admin_dashboard(request, section)
    return render_dashboard(request, section)


def _dashboard_context(request, section):
    """Apply the shared section permissions before any page is rendered."""
    allowed = {key for key, _ in NAV[request.user.role]}
    if request.user.role == 'patient':
        allowed |= {'addresses'}
    if request.user.role in ['admin', 'pharmacist']:
        allowed |= {'medications', 'suppliers', 'reorders'}
    if request.user.role in ['pharmacist', 'driver']:
        allowed.add('orders')
    if section not in allowed:
        raise Http404
    return shell(request.user, section)


def render_dashboard(request, section='overview'):
    """Preserve existing /app/<section>/ links while selecting a named page view."""
    _dashboard_context(request, section)
    from . import dashboard_views as pages
    if section == 'disputes':
        from core.features.disputes.views import list_view
        return list_view(request)
    if section == 'pharmacies' and request.user.role == 'patient':
        return pages.pharmacy_search_view(request)
    page_views = {
        'prescriptions': pages.prescriptions_view,
        'orders': pages.orders_view,
        'queue': pages.order_queue_view,
        'orderhistory': pages.order_history_view,
        'deliveries': pages.deliveries_view,
        'history': pages.delivery_history_view,
        'tracking': pages.order_status_view,
        'inventory': pages.inventory_view,
        'alerts': pages.inventory_alerts_view,
        'users': pages.users_view,
        'pharmacies': pages.pharmacies_view,
        'medications': pages.medications_view,
        'suppliers': pages.suppliers_view,
        'reorders': pages.reorders_view,
        'reminders': pages.reminders_view,
        'reviews': pages.reviews_view,
        'addresses': pages.addresses_view,
        'overview': pages.overview_view,
        'profile': pages.profile_view,
        'notifications': pages.notifications_view,
        'analytics': pages.analytics_view,
        'earnings': pages.delivery_charges_view,
        'drivers': pages.drivers_view,
        'settings': pages.settings_view,
    }
    return page_views[section](request)


@login_required(login_url='auth')
def resource_form_view(request,resource,pk=None):
    if resource not in FORMS or resource == 'profile': raise Http404
    item = get_object_or_404(scoped(resource,request.user),pk=pk) if pk else None
    if not may_edit(resource,request.user,item): raise PermissionDenied
    form = resource_form(resource,request.user,request.POST or None,request.FILES or None,item)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        if resource in ['addresses','payments']: obj.user = request.user
        if resource in ['prescriptions','reminders']: obj.patient = request.user
        if resource == 'reorders': obj.requested_by = request.user
        if resource == 'reviews':
            obj.patient = request.user; obj.pharmacy = obj.order.pharmacy; obj.driver = obj.order.driver
        with transaction.atomic():
            if resource in ['addresses','payments'] and obj.is_default:
                scoped(resource,request.user).exclude(pk=obj.pk).update(is_default=False)
            obj.save(); form.save_m2m()
        messages.success(request,'Saved successfully.')
        return redirect('dashboard_section',section=resource)
    ctx = shell(request.user,resource)
    ctx.update(form=form,resource=resource,is_edit=bool(item))
    singular={'prescriptions':'Prescription','reminders':'Reminder','reviews':'Review','addresses':'Address','payments':'Payment Method','inventory':'Inventory Item','medications':'Medication','pharmacies':'Pharmacy','suppliers':'Supplier','reorders':'Reorder Request'}
    ctx['form_title']=('Edit '+singular.get(resource,resource.title())) if item else {
        'prescriptions':'Upload Prescription','reviews':'Rate Your Order','reorders':'New Reorder Request',
    }.get(resource,'Add '+singular.get(resource,resource.title()))
    ctx['submit_label']='Submit Prescription' if resource=='prescriptions' and not item else 'Save Changes' if item else 'Save'
    return render(request,'dashboard/form.html',ctx)




@login_required(login_url='auth')
def order_detail_view(request,pk):
    order = get_object_or_404(scoped('orders',request.user),pk=pk)
    ctx = shell(request.user,'orders'); ctx['order'] = order
    return render(request,'orders/detail.html',ctx)


@login_required(login_url='auth')
@require_POST
def resource_action_view(request,resource,pk,operation):
    item = get_object_or_404(scoped(resource,request.user),pk=pk)
    role = request.user.role
    if resource == 'orders':
        try:
            if operation == 'accept': accept_delivery(order_id=pk, actor=request.user)
            elif operation == 'deliver': complete_order(order_id=pk, actor=request.user, proof=request.FILES.get('proof_of_delivery'))
            elif operation == 'status': change_order_status(order_id=pk, actor=request.user, status=request.POST.get('status'))
            elif operation == 'paid':
                from core.features.payments.services import record_cash_payment
                record_cash_payment(order_id=pk, actor=request.user)
            else: raise PermissionDenied
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
        return redirect('order_detail', pk=pk)
    if resource == 'prescriptions' and operation == 'review' and role in ['pharmacist','admin']:
        decision = request.POST.get('status')
        if decision not in ['approved','rejected']: raise PermissionDenied
        kind = request.POST.get('kind','single_use')
        if kind not in Prescription.Kind.values: raise PermissionDenied
        try: refills = int(request.POST.get('refills_remaining','0'))
        except ValueError: raise PermissionDenied
        if refills < 0: raise PermissionDenied
        item.status = decision; item.reviewed_by = request.user; item.review_notes = request.POST.get('review_notes','')
        if decision == 'approved': item.kind = kind; item.refills_remaining = refills
        item.save()
    elif resource == 'prescriptions' and operation == 'refill' and role == 'patient':
        if item.status != 'approved' or item.is_voided or item.expiry_date < timezone.localdate() or item.kind != 'repeat' or item.refills_remaining < 1:
            messages.error(request,'This prescription has no available refills.')
        else:
            request.session['checkout_prescription'] = item.pk
            return redirect('dashboard_section',section='pharmacies')
    elif resource == 'notifications' and operation == 'read':
        item.read_at = timezone.now(); item.save()
    elif resource == 'reminders' and operation == 'toggle' and role == 'patient':
        item.active = not item.active; item.save(update_fields=['active','updated_at'])
    elif resource == 'users' and role == 'admin' and operation == 'role':
        new_role = request.POST.get('role')
        if new_role not in User.Role.values or item.pk == request.user.pk: raise PermissionDenied
        item.role = new_role
        item.is_staff = new_role == 'admin'
        if new_role != 'admin': item.is_superuser = False
        item.save()
    elif resource == 'users' and role == 'admin' and operation == 'active':
        if item.pk == request.user.pk: raise PermissionDenied
        item.is_active = not item.is_active; item.save()
    elif resource == 'reorders' and operation == 'status' and role in ['admin','pharmacist']:
        try: change_reorder_status(reorder_id=pk, actor=request.user, status=request.POST.get('status'))
        except ValidationError as exc: messages.error(request, '; '.join(exc.messages)); return redirect('dashboard_section',section=resource)
    elif operation == 'delete' and may_edit(resource,request.user,item):
        if resource == 'prescriptions': item.deleted_at = timezone.now(); item.save()
        else: item.delete()
    else: raise PermissionDenied
    messages.success(request,'Updated successfully.')
    return redirect('dashboard_section',section=resource)


@login_required(login_url='auth')
def medication_catalogue_view(request,pk):
    if request.user.role != 'patient': raise PermissionDenied
    pharmacy = get_object_or_404(Pharmacy,pk=pk,active=True)
    inventory = scoped('inventory',request.user).filter(pharmacy=pharmacy).select_related('medication')
    if request.GET.get('q'): inventory = inventory.filter(Q(medication__name__icontains=request.GET['q']) | Q(medication__generic_name__icontains=request.GET['q']))
    if request.GET.get('category'): inventory=inventory.filter(medication__category=request.GET['category'])
    if request.GET.get('rx') == '1': inventory=inventory.filter(medication__requires_prescription=True)
    pharmacy.rating=pharmacy.reviews.aggregate(value=Avg('rating'))['value']
    pharmacy.open_now=opening_state(pharmacy)
    ctx = shell(request.user,'pharmacies'); ctx.update(pharmacy=pharmacy,inventory=inventory,search=request.GET.get('q',''),
        categories=InventoryItem.objects.filter(pharmacy=pharmacy,active=True).values_list('medication__category',flat=True).distinct(),
        selected_category=request.GET.get('category',''),profile_view=request.GET.get('view')=='profile',
        pharmacy_reviews=Review.objects.filter(pharmacy=pharmacy,patient=request.user).order_by('-created_at'),
        staff=pharmacy.staff.select_related('user').all())
    return render(request,'orders/catalogue.html',ctx)


@login_required(login_url='auth')
@require_POST
def cart_update_view(request,pk):
    if request.user.role != 'patient': raise PermissionDenied
    item = get_object_or_404(scoped('inventory',request.user),pk=pk)
    cart = request.session.get('cart',{})
    try: quantity = int(request.POST.get('quantity','1'))
    except ValueError: quantity = -1
    if quantity < 0 or quantity > item.stock:
        messages.error(request,'Choose a quantity within available stock.')
    elif quantity == 0: cart.pop(str(pk),None)
    else:
        if cart and InventoryItem.objects.filter(pk__in=cart).exclude(pharmacy_id=item.pharmacy_id).exists():
            messages.error(request,'Please check out your current pharmacy cart before changing pharmacies.'); return redirect('cart')
        cart[str(pk)] = quantity
    request.session['cart'] = cart
    return redirect('cart')


@login_required(login_url='auth')
def cart_view(request):
    if request.user.role != 'patient': raise PermissionDenied
    saved = request.session.get('cart',{})
    items = list(scoped('inventory',request.user).filter(pk__in=saved).select_related('medication','pharmacy'))
    rows = [{'item':i,'quantity':saved[str(i.pk)],'total':i.price * saved[str(i.pk)]} for i in items]
    subtotal = sum((row['total'] for row in rows),Decimal('0'))
    error = None
    if request.method == 'POST' and rows:
        try:
            delivery_type = request.POST.get('delivery_type','delivery')
            address = get_object_or_404(Address,user=request.user,pk=request.POST.get('address')) if delivery_type == 'delivery' else None
            prescription_id = request.POST.get('prescription')
            prescription = get_object_or_404(Prescription,patient=request.user,pk=prescription_id,deleted_at__isnull=True) if prescription_id else None
            if delivery_type not in Order.DeliveryType.values: raise ValidationError('Choose delivery or pickup.')
            if prescription and (prescription.status != 'approved' or prescription.is_voided or prescription.expiry_date < timezone.localdate()): raise ValidationError('Choose a valid approved prescription.')
            if any(i.medication.requires_prescription for i in items) and not prescription: raise ValidationError('A prescription is required for these medications.')
            if len({i.pharmacy_id for i in items}) != 1: raise ValidationError('Choose items from one pharmacy.')
            if delivery_type == 'delivery' and not items[0].pharmacy.delivery_available: raise ValidationError('This pharmacy offers pickup only.')
            fee = Decimal('4.99') if delivery_type == 'delivery' and subtotal < 30 else Decimal('0')
            order = place_order(patient=request.user, cart=saved, delivery_type=delivery_type,
                                address=address, prescription=prescription)
            request.session['cart'] = {}; request.session.pop('checkout_prescription',None)
            messages.success(request,'Order placed.'); return redirect('order_detail',pk=order.pk)
        except ValidationError as exc: error = "; ".join(exc.messages)
    ctx = shell(request.user,'orders')
    display_fee=Decimal('4.99') if subtotal < 30 and request.POST.get('delivery_type','delivery') != 'pickup' else Decimal('0')
    ctx.update(cart_rows=rows,subtotal=subtotal,display_fee=display_fee,display_total=subtotal+display_fee,error=error,addresses=scoped('addresses',request.user),prescriptions=scoped('prescriptions',request.user).filter(status='approved',voided_at__isnull=True,expiry_date__gte=timezone.localdate()),selected_prescription=request.session.get('checkout_prescription'))
    return render(request,'orders/cart.html',ctx)



