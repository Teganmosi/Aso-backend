from django.urls import path
from .views import PaymentInitializeView, PaymentWebhookView, PaymentVerifyView

urlpatterns = [
    path('initialize/', PaymentInitializeView.as_view(), name='payment-initialize'),
    path('webhook/paystack/', PaymentWebhookView.as_view(), name='payment-webhook-paystack'),
    path('verify/<str:reference>/', PaymentVerifyView.as_view(), name='payment-verify'),
    path('verify/', PaymentVerifyView.as_view(), name='payment-verify-query'),
]
