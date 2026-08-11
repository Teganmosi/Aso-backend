from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CSRFTokenView, RegisterView, LoginView, LogoutView, MeView, AddressViewSet

router = DefaultRouter()
router.register('addresses', AddressViewSet, basename='address')

urlpatterns = [
    path('csrf/', CSRFTokenView.as_view(), name='csrf-token'),
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('login/', LoginView.as_view(), name='auth-login'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('me/', MeView.as_view(), name='auth-me'),
    path('', include(router.urls)),
]
