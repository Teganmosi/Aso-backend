from django.urls import path
from apps.orders.views import OrderListCreateView, OrderDetailView, OrderAcceptView, OrderPreparingView, OrderReadyView
from apps.deliveries.views import OrderDeliveryDetailView

urlpatterns = [
    path('', OrderListCreateView.as_view(), name='order-list-create'),
    path('<uuid:order_id>/', OrderDetailView.as_view(), name='order-detail'),
    path('<uuid:order_id>/accept/', OrderAcceptView.as_view(), name='order-accept'),
    path('<uuid:order_id>/preparing/', OrderPreparingView.as_view(), name='order-preparing'),
    path('<uuid:order_id>/ready/', OrderReadyView.as_view(), name='order-ready'),
    path('<uuid:order_id>/delivery/', OrderDeliveryDetailView.as_view(), name='order-delivery-detail'),
]
