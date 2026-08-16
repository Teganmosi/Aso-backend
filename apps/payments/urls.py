from django.urls import path
from .views import PaymentInitializeView, PaymentWebhookView

urlpatterns = [
    path('initialize/', PaymentInitializeView.as_view(), name='payment-initialize'),
    path('webhook/paystack/', PaymentWebhookView.as_view(), name='payment-webhook-paystack'),
]