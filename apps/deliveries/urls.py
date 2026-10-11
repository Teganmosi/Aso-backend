from django.urls import path
from apps.deliveries.views import (
    DeliveryStatusUpdateView,
    OrderDeliveryDetailView,
    OrderWaybillView,
    DeliveryQuoteView,
    DellymanWebhookView
)

urlpatterns = [
    path('quote/', DeliveryQuoteView.as_view(), name='delivery-quote'),
    path('webhook/dellyman/', DellymanWebhookView.as_view(), name='dellyman-webhook'),
    path('<uuid:delivery_id>/update-status/', DeliveryStatusUpdateView.as_view(), name='delivery-status-update'),
]
