from django.contrib import admin
from django.urls import path, include, re_path
from apps.common.views import ImageUploadView, serve_media
from apps.accounts.views import MeView
from django.http import HttpResponseRedirect
from django.conf import settings
from apps.payments.views import PaymentWebhookView

def order_redirect_view(request):
    query = request.META.get('QUERY_STRING', '')
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
    target = f'{frontend_url}/orders'
    if query:
        target = f'{target}?{query}'
    return HttpResponseRedirect(target)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/auth/', include('apps.accounts.urls')),
    path('api/v1/me/', MeView.as_view(), name='api-me'),
    path('api/v1/media/upload/', ImageUploadView.as_view(), name='media-upload'),
    # Uploaded images (product photos, logos, banners). Public by design: only
    # re-encoded images are ever written here (apps/common/media_storage.py).
    re_path(r'^media/(?P<path>.+)$', serve_media, name='media'),
    path('api/v1/vendors/', include('apps.vendors.urls')),
    path('api/v1/cart/', include('apps.cart.urls')),
    path('api/v1/orders/', include('apps.orders.urls')),
    path('api/v1/', include('apps.products.urls')),
    path('api/v1/payments/', include('apps.payments.urls')),
    path('api/v1/deliveries/', include('apps.deliveries.urls')),
    path('api/v1/payouts/', include('apps.payouts.urls')),
    path('orders', order_redirect_view, name='order-redirect-bare'),
    path('orders/', order_redirect_view, name='order-redirect'),
    path('webhook/flow', PaymentWebhookView.as_view(), name='payment-webhook-flow-bare'),
    path('webhook/flow/', PaymentWebhookView.as_view(), name='payment-webhook-flow'),
]