from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CSRFTokenView, RegisterView, LoginView, LogoutView, MeView, AddressViewSet, UserMeasurementsView,
    PasswordResetRequestView, PasswordResetConfirmView,
)

router = DefaultRouter()
router.register('addresses', AddressViewSet, basename='address')

urlpatterns = [
    path('csrf/', CSRFTokenView.as_view(), name='csrf-token'),
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('login/', LoginView.as_view(), name='auth-login'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('password-reset/', PasswordResetRequestView.as_view(), name='password-reset'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    path('me/', MeView.as_view(), name='auth-me'),
    path('profile/measurements/', UserMeasurementsView.as_view(), name='user-measurements'),
    path('', include(router.urls)),
]
