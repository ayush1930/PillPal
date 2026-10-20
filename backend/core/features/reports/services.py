from django.db.models import Sum


def order_summary(orders):
    completed = orders.filter(status='delivered')
    totals = completed.aggregate(total=Sum('total'), delivery_fees=Sum('delivery_fee'))
    return [('Completed orders', completed.count()), ('Order totals', totals['total'] or 0), ('Delivery fees', totals['delivery_fees'] or 0)]
