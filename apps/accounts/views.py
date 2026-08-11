from django.contrib.auth import login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_protect
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from rest_framework import status, permissions

from .serializers import (
    UserSerializer, RegisterSerializer, LoginSerializer, AddressSerializer
)
from .services import create_user_service, create_address_service
from .selectors import get_user_addresses
from .models import Address


class CSRFTokenView(APIView):
    """
    Sets CSRF token cookie and returns CSRF token string for web clients.
    """
    permission_classes = [permissions.AllowAny]

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        csrf_token = get_token(request)
        return Response({
            'success': True,
            'csrf_token': csrf_token
        })


class RegisterView(APIView):
    """
    Registers a new user account, creates CustomerProfile, and authenticates via Session cookie.
    """
    permission_classes = [permissions.AllowAny]

    @method_decorator(csrf_protect)
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = create_user_service(**serializer.validated_data)
        login(request, user)

        return Response({
            'success': True,
            'message': 'Registration successful.',
            'user': UserSerializer(user).data
        }, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    """
    Authenticates user credentials and establishes an HttpOnly Session cookie.
    """
    permission_classes = [permissions.AllowAny]

    @method_decorator(csrf_protect)
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data['user']
        login(request, user)

        return Response({
            'success': True,
            'message': 'Login successful.',
            'user': UserSerializer(user).data
        }, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """
    Logs out user and flushes the server session.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response({
            'success': True,
            'message': 'Logged out successfully.'
        }, status=status.HTTP_200_OK)


class MeView(APIView):
    """
    Returns authenticated user profile details and saved shipping addresses.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        addresses = get_user_addresses(request.user)
        return Response({
            'success': True,
            'user': UserSerializer(request.user).data,
            'addresses': AddressSerializer(addresses, many=True).data
        })


class AddressViewSet(ModelViewSet):
    """
    ViewSet for managing user shipping addresses.
    """
    serializer_class = AddressSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        address = create_address_service(user=request.user, address_data=serializer.validated_data)
        return Response({
            'success': True,
            'address': AddressSerializer(address).data
        }, status=status.HTTP_201_CREATED)
