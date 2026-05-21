from django.urls import path
from .views import (
    RegisterView, ReSendVerificationEmailView, 
    VerifyEmailView, LoginView, PasswordResetView, 
    SetNewPassword, LogoutView
)   

# using this for now
urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path("login/", LoginView.as_view(), name="login"),
    path("resend-verification/", ReSendVerificationEmailView.as_view(), name="sendVerification"),
    path("verify-email/", VerifyEmailView.as_view(), name="verify_email"),
    path('password-reset/', PasswordResetView.as_view(), name='password-reset'),
    path('confirm-password/', SetNewPassword.as_view(), name='password-reset-confirm'),
    path('logout/', LogoutView.as_view(), name='logout'),
]
