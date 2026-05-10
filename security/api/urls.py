from django.urls import path
from .views import RegisterView, SendVerificationEmailView, VerifyEmailView, LoginView, PasswordResetView, SetNewPassword


urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path("login/", LoginView.as_view(), name="login"),
    path("send-verification/", SendVerificationEmailView.as_view(), name="sendVerification"),
    path("verify-email/", VerifyEmailView.as_view(), name="verify_email"),
    path('password-reset/', PasswordResetView.as_view(), name='password-reset'),
    path('confirmpassword/', SetNewPassword.as_view(), name='password-reset-confirm'),
]
