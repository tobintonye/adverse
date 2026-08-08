from rest_framework.permissions import AllowAny, IsAuthenticated
from .serializers import (
    RegisterSerializer, LoginSerializer,
    PasswordResetRequestSerializer, SetNewPasswordSerializer, RoleSelectionSerializer,
)
from django.contrib.auth import get_user_model
from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from core.services.email_service import (send_verification_email, send_password_reset_email_safe)
from django.contrib.auth.tokens import default_token_generator
from ..tokens import email_verification_token 
from django.utils.http import urlsafe_base64_decode
from django.db import transaction
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from ..models import CustomUser
from axes.decorators import axes_dispatch
from django.utils.decorators import method_decorator
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_register"

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        user = User.objects.get(id=response.data['id'])
        send_verification_email(user, request)
        return Response(
            {"detail": "Registration successful. Please check your email to verify your account."},
            status=status.HTTP_201_CREATED
        )


@method_decorator(axes_dispatch, name='dispatch')
class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            user = serializer.validated_data["user"]
            refresh = RefreshToken.for_user(user)
            return Response({
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            }, status=status.HTTP_200_OK)
        return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)


class ReSendVerificationEmailView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_resend_verification"

    def post(self, request):
        email = request.data.get('email')
        if email:
            try:
                user = User.objects.get(email=email)
                if not user.is_active:
                    send_verification_email(user, request)
            except User.DoesNotExist:
                pass
        return Response({
            "detail": "If the email exists and is unverified, a verification link has been sent."
        }, status=status.HTTP_200_OK)


class VerifyEmailView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        uid = request.data.get("uid")
        token = request.data.get("token")
        if not uid or not token:
            return Response({"error": "Invalid or expired verification link."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            uid_decoded = urlsafe_base64_decode(uid).decode()
            user = User.objects.get(pk=uid_decoded)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({"error": "Invalid or expired verification link."}, status=status.HTTP_400_BAD_REQUEST)

        if not email_verification_token.check_token(user, token):
            return Response({"error": "Invalid or expired verification link."}, status=status.HTTP_400_BAD_REQUEST)

        if user.is_active:
            return Response({"message": "Email already verified."}, status=status.HTTP_200_OK)

        with transaction.atomic():
            user.is_active = True
            user.save(update_fields=["is_active"])
            return Response({"message": "Email verified successfully."}, status=status.HTTP_200_OK)


class PasswordResetView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_password_reset"

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            try:
                user = User.objects.get(email=email)
                send_password_reset_email_safe(user, request)
            except User.DoesNotExist:
                send_password_reset_email_safe(None, request)
            return Response({"detail": "If this email exists, a password reset link has been sent."}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SetNewPassword(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_password_reset"

    def post(self, request):
        uid = request.data.get("uid")
        token = request.data.get("token")
        if not uid or not token:
            return Response({"error": "Invalid or expired verification link."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            uid_decoded = urlsafe_base64_decode(uid).decode()
            user = User.objects.get(pk=uid_decoded)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({"error": "Invalid or expired verification link."}, status=status.HTTP_400_BAD_REQUEST)

        # Password reset correctly keeps default_token_generator only
        # verification uses the separate email_verification_token.
        if not default_token_generator.check_token(user, token):
            return Response({"error": "Invalid or expired verification link."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = SetNewPasswordSerializer(data=request.data, context={"user": user})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response({"detail": "Password reset successful."}, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """
    JWT logout: blacklist the refresh token. The access token stays valid
    until it naturally expires (inherent JWT limitation) — keep
    SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'] short so this window stays small.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"error": "Refresh token is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh_token)
            if token["user_id"] != request.user.id:
                return Response({"error": "Token mismatch."}, status=status.HTTP_403_FORBIDDEN)
            token.blacklist()
        except TokenError:
            return Response({"error": "Invalid or expired token."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Logout successful."}, status=status.HTTP_205_RESET_CONTENT)


class SelectUserRoleView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = RoleSelectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        chosen_role = serializer.validated_data["role"]

        try:
            with transaction.atomic():
                user = CustomUser.objects.select_for_update().get(pk=request.user.pk)
                if user.role:
                    return Response({
                        "detail": f"You already selected your role as {user.role}."
                    }, status=status.HTTP_400_BAD_REQUEST)
                user.role = chosen_role
                user.save()
                return Response(
                    {"message": f"Role set to {user.role}. Please complete your profile."},
                    status=status.HTTP_200_OK
                )
        except Exception:
            logger.exception("SelectUserRoleView failed for user %s", request.user.pk)
            return Response(
                {"error": "Something went wrong. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )