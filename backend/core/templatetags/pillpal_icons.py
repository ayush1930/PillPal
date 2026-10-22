import json
from pathlib import Path

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()
ICONS = json.loads(Path(__file__).with_name('icon_paths.json').read_text(encoding='utf-8'))
NAV_ICONS = {
    'overview':'Home', 'users':'Users', 'prescriptions':'FileText', 'orders':'Package',
    'tracking':'MapPin', 'pharmacies':'Building', 'reminders':'Bell', 'reviews':'Star',
    'notifications':'Bell', 'profile':'User', 'queue':'Clipboard', 'inventory':'Archive',
    'alerts':'AlertTriangle', 'reorders':'RefreshCw', 'orderhistory':'History',
    'drivers':'Truck', 'deliveries':'Truck', 'history':'History', 'earnings':'DollarSign',
    'analytics':'BarChart2', 'settings':'Settings', 'disputes':'AlertCircle',
    'suppliers':'Building', 'addresses':'MapPin', 'payments':'CreditCard',
}


@register.simple_tag
def icon(name, size=18):
    if name not in ICONS:
        raise ValueError(f'Unknown PillPal icon: {name}')
    size = max(1, min(int(size), 256))
    viewbox = '0 0 32 32' if name == 'Logo' else '0 0 24 24'
    attributes = '' if name == 'Logo' else ' stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"'
    # Icon paths are trusted bundled assets, not user input.
    return format_html('<svg class="svg-icon{}" width="{}" height="{}" viewBox="{}" fill="none"{} aria-hidden="true" focusable="false">{}</svg>',
                       ' brand-icon' if name == 'Logo' else '',size,size,viewbox,mark_safe(attributes),mark_safe(ICONS[name]))


@register.simple_tag
def nav_icon(section, role='patient', size=16):
    name = 'Building' if section == 'profile' and role == 'pharmacist' else NAV_ICONS.get(section,'Home')
    return icon(name,size)


@register.simple_tag
def stat_icon(label, size=22):
    name = {'Orders':'Package', 'Active orders':'Truck', 'Prescriptions':'FileText',
            'Unread notifications':'Bell', 'Completed orders':'CheckCircle',
            'Order totals':'DollarSign', 'Delivery fees':'DollarSign'}.get(label,'Activity')
    return icon(name,size)


@register.simple_tag(takes_context=True)
def query_url(context, **updates):
    params=context['request'].GET.copy()
    params.pop('partial',None)
    for key,value in updates.items():
        if value in ['',None,False]: params.pop(key,None)
        else: params[key]=str(value)
    return '?' + params.urlencode()


@register.simple_tag
def rating_stars(value, size=14):
    try: score=float(value)
    except (TypeError,ValueError): score=0
    parts=[format_html('<span class="{}">{}</span>','star-filled' if position <= round(score) else 'star-empty',icon('Star',size)) for position in range(1,6)]
    return format_html('<span class="stars" role="img" aria-label="{} out of 5">{}</span>',score,mark_safe(''.join(str(p) for p in parts)))
