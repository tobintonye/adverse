from django.urls import path
from .views import RegisterView, SendVerificationEmailView, VerifyEmailView, LoginView

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path("login/", LoginView.as_view(), name="login"),
    path("send-verification/", SendVerificationEmailView.as_view(), name="sendVerification"),
    path("verify-email/", VerifyEmailView.as_view(), name="verify_email"),
]
