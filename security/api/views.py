from django.shortcuts import render
from rest_framework.permissions import AllowAny
from .serializers import RegisterSerializer, LoginSerializer, PasswordResetRequestSerializer, SetNewPasswordSerializer
from rest_framework.authtoken.models import Token
from django.contrib.auth import get_user_model
from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from ..views import sendVerificationEmail, sendPasswordResetLink, delayed_send_email
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_decode
from django.db import transaction
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()

class RegisterView(generics.CreateAPIView): 
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        user = User.objects.get(id=response.data['id'])
        
        sendVerificationEmail(user, request)
        return Response(
            {"detail": "Registration successful. Please check your email to verify your account."},
            status=status.HTTP_201_CREATED
        )

class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request): 
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data["user"]
            refresh = RefreshToken.for_user(user)
            return Response({
                "refresh":str(refresh), 
                "access":str(refresh.access_token),
            },  status=status.HTTP_200_OK )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class SendVerificationEmailView(APIView):
    permission_classes = [AllowAny]

    def post(self, request): 
        email = request.data.get('email')
        if email:
            try: 
                user = User.objects.get(email=email)
                if not user.is_active:
                    sendVerificationEmail(user, request) # for dev
            except User.DoesNotExist:
                pass
        return Response({
                "detail":
                "If the email exists and is unverified, a verification link has been sent."
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
            return Response({
                "error": "Invalid or expired verification link."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not default_token_generator.check_token(user, token):
            return Response({"error": "Invalid or expired verification link."}, status=status.HTTP_400_BAD_REQUEST)
        if user.is_active: # later to be changed to is_email_verified()
            return Response( {"message": "Email already verified."}, status=status.HTTP_200_OK)

        with transaction.atomic():
            user.is_active = True
            user.save(update_fields=["is_active"])

            return Response(
                {"message": "Email verified successfully."},
                status=status.HTTP_200_OK
            )

class PasswordResetView(APIView):
    permission_classes = [AllowAny]

    def post(self, request): 
        serializer = PasswordResetRequestSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            try: 
                user = User.objects.get(email=email)
                sendPasswordResetLink(user, request)
            except User.DoesNotExist: 
                delayed_send_email(None, request)
            return Response({"detail": "If this email exists, a password reset link has been sent."}, status=status.HTTP_200_OK)
        
class setNewPassword(APIView): 
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
        if not default_token_generator.check_token(user, token):
            return Response({"error": "Invalid or expired verification link."}, status=status.HTTP_400_BAD_REQUEST)
        serializer = SetNewPasswordSerializer(
            data=request.data,
            context={"user":user}
        )

        if not serializer.is_valid():
            return Response(serializer.error, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response({"detail": "Password reset successful."}, status=status.HTTP_200_OK)