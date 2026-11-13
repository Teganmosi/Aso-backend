from django.contrib.auth import login, logout
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
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
from .models import Address, CustomerProfile, User
from .throttles import LoginThrottle, PasswordResetThrottle, RegisterThrottle
from apps.common.notifications import send_password_reset_email


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
    throttle_classes = [RegisterThrottle]

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
    throttle_classes = [LoginThrottle]

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
    Allows updating personal details (first_name, last_name, phone_number) via PATCH.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        addresses = get_user_addresses(request.user)
        return Response({
            'success': True,
            'user': UserSerializer(request.user).data,
            'addresses': AddressSerializer(addresses, many=True).data
        })

    def patch(self, request):
        from .models import User
        user = request.user
        data = request.data

        if 'first_name' in data:
            user.first_name = str(data['first_name']).strip()
        if 'last_name' in data:
            user.last_name = str(data['last_name']).strip()
        if 'phone_number' in data:
            phone = str(data['phone_number']).strip()
            if phone and User.objects.filter(phone_number=phone).exclude(id=user.id).exists():
                return Response(
                    {'detail': 'This phone number is already registered to another account.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            user.phone_number = phone

        user.save()
        return Response({
            'success': True,
            'message': 'Profile updated successfully.',
            'user': UserSerializer(user).data
        }, status=status.HTTP_200_OK)


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


class UserMeasurementsView(APIView):
    """
    GET: Retrieve authenticated user's saved 'My Aso Fit' bespoke measurements.
    PUT/PATCH: Update saved body measurements for 1-click checkout.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile, _ = CustomerProfile.objects.get_or_create(user=request.user)
        return Response({
            'success': True,
            'saved_measurements': profile.saved_measurements or {}
        })

    def put(self, request):
        return self._save_measurements(request)

    def patch(self, request):
        return self._save_measurements(request)

    def _save_measurements(self, request):
        profile, _ = CustomerProfile.objects.get_or_create(user=request.user)
        measurements = request.data.get('measurements', request.data)
        if not isinstance(measurements, dict):
            return Response(
                {'detail': 'Measurements must be a JSON object.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        profile.saved_measurements = measurements
        profile.save(update_fields=['saved_measurements', 'updated_at'])
        return Response({
            'success': True,
            'message': 'My Aso Fit measurements saved successfully.',
            'saved_measurements': profile.saved_measurements
        }, status=status.HTTP_200_OK)


class PasswordResetRequestView(APIView):
    """
    POST {email}. Emails a one-time link to choose a new password.
    Always answers the same way so it can't be used to discover who has an account.
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [PasswordResetThrottle]

    def post(self, request):
        email = str(request.data.get('email', '')).strip().lower()
        if email:
            user = User.objects.filter(email__iexact=email, is_active=True).first()
            if user and user.has_usable_password():
                send_password_reset_email(user)
        return Response({
            'success': True,
            'message': 'If that email has an Aso account, we’ve sent a link to reset your password. It works for 2 hours.'
        })


class PasswordResetConfirmView(APIView):
    """POST {uid, token, new_password}. Sets the new password and signs the user out everywhere."""
    permission_classes = [permissions.AllowAny]
    throttle_classes = [PasswordResetThrottle]

    def post(self, request):
        uid = str(request.data.get('uid', ''))
        token = str(request.data.get('token', ''))
        new_password = str(request.data.get('new_password', ''))
        invalid = Response({'success': False, 'error': {
            'code': 'invalid_reset_link',
            'message': 'This reset link is invalid or has expired. Please request a new one.',
        }}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(pk=force_str(urlsafe_base64_decode(uid)), is_active=True)
        except (User.DoesNotExist, ValueError, TypeError, OverflowError, ValidationError):
            return invalid
        if not default_token_generator.check_token(user, token):
            return invalid

        if len(new_password) < 8:
            return Response({'success': False, 'error': {
                'code': 'weak_password', 'message': 'Your new password must be at least 8 characters.',
            }}, status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_password(new_password, user)
        except ValidationError as exc:
            return Response({'success': False, 'error': {
                'code': 'weak_password', 'message': ' '.join(exc.messages),
            }}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)  # also invalidates this token and other sessions' auth hash
        user.save(update_fields=['password'])
        return Response({'success': True, 'message': 'Your password has been changed. You can sign in now.'})
