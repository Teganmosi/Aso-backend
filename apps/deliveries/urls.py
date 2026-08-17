from django.urls import path
from apps.deliveries.views import DeliveryStatusUpdateView

urlpatterns = [
    path('<uuid:delivery_id>/update-status/', DeliveryStatusUpdateView.as_view(), name='delivery-status-update'),
]