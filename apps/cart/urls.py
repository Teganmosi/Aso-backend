from django.urls import path
from apps.cart.views import CartDetailView, CartItemAddView, CartItemDetailView

urlpatterns = [
    path('', CartDetailView.as_view(), name='cart-detail'),
    path('items/', CartItemAddView.as_view(), name='cart-item-add'),
    path('items/<uuid:item_id>/', CartItemDetailView.as_view(), name='cart-item-detail'),
]
