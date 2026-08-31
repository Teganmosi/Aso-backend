from django.contrib import admin
from django.urls import path, include
from apps.accounts.views import MeView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/auth/', include('apps.accounts.urls')),
    path('api/v1/me/', MeView.as_view(), name='api-me'),
    path('api/v1/vendors/', include('apps.vendors.urls')),
    path('api/v1/cart/', include('apps.cart.urls')),
    path('api/v1/orders/', include('apps.orders.urls')),
    path('api/v1/', include('apps.products.urls')),
    path('api/v1/payments/', include('apps.payments.urls')),
    path('api/v1/deliveries/', include('apps.deliveries.urls')),
    path('api/v1/payouts/', include('apps.payouts.urls')),
]

