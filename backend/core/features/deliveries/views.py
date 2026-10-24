from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from core.common.permissions import IsDriverOrAdmin
from core.features.orders.models import Order

class DeliveryActionsMixin:

    @action(detail=True, methods=['post'], permission_classes=[IsDriverOrAdmin])
    def accept_delivery(self, request, pk=None):
        order = self.get_object()
        if order.driver_id and order.driver != request.user:
            return Response({'detail': 'Delivery already assigned.'}, status=status.HTTP_409_CONFLICT)
        order.driver = request.user
        order.status = Order.Status.OUT_FOR_DELIVERY
        order.save(update_fields=['driver', 'status', 'updated_at'])
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=['post'], permission_classes=[IsDriverOrAdmin])
    def deliver(self, request, pk=None):
        order = self.get_object()
        order.mark_delivered()
        return Response(self.get_serializer(order).data)
