from django.urls import path
from . import views

app_name = "security"


urlpatterns = [
    path('register/', views.registerAccount, name='register'),
    path('login/', views.loginAccount, name='login'),
    path('logout/', views.logoutAccount, name='logout'),
    path('resend-verification/', views.resendVerificationLink, name='resendVerification'),
    path('verify-email/<str:uidb64>/<str:token>/', views.verifyEmail, name='verifyemail'),
    path('verification-pending/', views.verification_pending, name="verificationpending"),
    path('post-login/', views.post_login, name='post_login'),
    path('password-reset/', views.passwordReset, name="passwordrest"),
    path('password-reset/done/', views.password_reset_done, name='passwordresetdone'),
    path('newpassword/<uidb64>/<token>/', views.new_password_request, name="newpasswordReset"), 
    path('password-reset-complete/', views.passwordRestComplete, name='resetcomplete'),
    path('reset-password/', views.resend_passwordreset_link, name="resendpasswordlink"),
    path('change-password/', views.change_password, name='change_password'),
    path('select-role/', views.selectuser_role, name='selectrole'),
]