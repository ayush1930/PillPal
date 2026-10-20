from pathlib import Path

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F
from django.urls import reverse
from django.utils import timezone

from core.features.notifications.models import Notification
from core.features.orders.models import Order
from .models import Dispute, DisputeUpdate


def visible_disputes(actor):
    disputes = Dispute.objects.select_related('order__patient', 'order__pharmacy', 'updated_by')
    if not actor.is_authenticated or not actor.is_active:
        return disputes.none()
    if actor.role == 'admin':
        return disputes
    if actor.role == 'patient':
        return disputes.filter(order__patient=actor)
    return disputes.none()


def validate_evidence(upload):
    if not upload:
        return upload
    if upload.size > 10 * 1024 * 1024:
        raise ValidationError('Evidence must be no larger than 10 MB.')
    extension = Path(upload.name).suffix.lower()
    if extension == '.pdf':
        valid = upload.read(5) == b'%PDF-'
        upload.seek(0)
        if not valid:
            raise ValidationError('Upload a valid PDF file or image.')
    elif extension in ['.jpg', '.jpeg', '.png', '.webp']:
        from PIL import Image
        try:
            image = Image.open(upload)
            image.verify()
            if image.format not in ['JPEG', 'PNG', 'WEBP']:
                raise ValueError
        except Exception as exc:
            raise ValidationError('Upload a valid PDF file or image.') from exc
        finally:
            upload.seek(0)
    else:
        raise ValidationError('Evidence must be a PDF, JPG, PNG or WebP file.')
    return upload


@transaction.atomic
def submit_dispute(*, actor, order_id, subject, category, description, evidence=None):
    if not actor.is_authenticated or not actor.is_active or actor.role != 'patient':
        raise PermissionDenied
    order = Order.objects.select_for_update().filter(pk=order_id, patient=actor).first()
    if order is None:
        raise PermissionDenied
    if order.disputes.filter(status__in=['open', 'under_review']).exists():
        raise ValidationError('This order already has an active dispute. View its progress instead.')
    dispute = Dispute(order=order, subject=subject.strip(), category=category,
                       description=description.strip(), evidence=validate_evidence(evidence))
    dispute.full_clean()
    dispute.save()
    DisputeUpdate.objects.create(dispute=dispute, actor=actor, to_status='open')
    from core.features.accounts.models import User
    for admin in User.objects.filter(role='admin', is_active=True):
        Notification.objects.create(user=admin, kind='dispute', title='New order dispute',
            body=f'Dispute #{dispute.pk} was submitted for order #{order.pk}.',
            link=reverse('admin_dispute_detail', args=[dispute.pk]))
    return dispute


@transaction.atomic
def review_dispute(*, actor, dispute_id, status, response, version):
    if not actor.is_authenticated or not actor.is_active or actor.role != 'admin':
        raise PermissionDenied
    dispute = Dispute.objects.select_for_update().select_related('order__patient').get(pk=dispute_id)
    transitions = {'open': ['open', 'under_review', 'resolved', 'rejected'],
        'under_review': ['under_review', 'resolved', 'rejected'],
        'resolved': ['under_review'], 'rejected': ['under_review']}
    if status not in transitions[dispute.status]:
        raise ValidationError('Invalid status change. A closed dispute must be reopened for review.')
    if status == 'under_review' and Dispute.objects.filter(order=dispute.order,
            status__in=['open', 'under_review']).exclude(pk=dispute.pk).exists():
        raise ValidationError('This order has another active dispute. Review that case before reopening this one.')
    response = response.strip()
    if len(response) > 4000:
        raise ValidationError('Keep your response within 4000 characters.')
    if status in ['resolved', 'rejected'] and not response:
        raise ValidationError('Explain the resolution or rejection before closing the dispute.')
    if status == dispute.status and response == dispute.admin_response:
        raise ValidationError('Change the status or response before saving.')
    closed_at = timezone.now() if status in ['resolved', 'rejected'] else None
    changed = Dispute.objects.filter(pk=dispute.pk, version=version).update(
        status=status, admin_response=response, updated_by=actor, closed_at=closed_at,
        version=F('version') + 1, updated_at=timezone.now())
    if not changed:
        raise ValidationError('Another administrator updated this dispute. Reload the page before saving.')
    DisputeUpdate.objects.create(dispute=dispute, actor=actor, from_status=dispute.status,
                                 to_status=status, response=response)
    Notification.objects.create(user=dispute.order.patient, kind='dispute',
        title='Your dispute was updated', body=f'Dispute #{dispute.pk}: {Dispute.Status(status).label}.',
        link=reverse('dispute_detail', args=[dispute.pk]))
    dispute.refresh_from_db()
    return dispute
