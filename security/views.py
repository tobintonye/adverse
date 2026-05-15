from django.shortcuts import render, redirect
from .forms import RegisterForm, LoginForm, PasswordResetForm, SetPasswordForm
from django.contrib.auth import get_user_model, login, logout
from django.contrib import messages
from .models import CustomUser
from django_ratelimit.decorators import ratelimit
from django.core.exceptions import ValidationError
from django.conf import settings
from django.core.mail import send_mail, BadHeaderError
from django.core.validators import validate_email
from django.urls import reverse
import smtplib
import socket
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.db import transaction
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
import threading
import time
import random
from rest_framework.exceptions import APIException

User = get_user_model()

def sendCustomEmail(subject, message, recipient_email): 
    try:
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [recipient_email])
    except BadHeaderError:
        raise ValidationError("There was a problem with the email header. Please try again later.")
    except smtplib.SMTPRecipientsRefused:
        raise ValidationError("This email address is not valid or refused by the email server.")
    except smtplib.SMTPDataError:
        raise ValidationError("There was an error sending your email. Please try again.")
    except smtplib.SMTPException:
        raise ValidationError("A mail server error occurred. Please try again later.")
    except socket.error:
        raise ValidationError("Network error. Please check your internet connection and try again.")
    except ImproperlyConfigured:
        raise ValidationError("Email service is currently not configured. Please contact support.")
    except Exception:
        raise ValidationError("An unexpected error occurred. Please try again later.")

def sendVerificationEmail(user, request): 
    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    verification_link = request.build_absolute_uri( 
        reverse("security:verifyemail", kwargs={"uidb64":uid, "token":token})
    )

    subject = "Verify your Adverse account"
    message = f"""Hi {user.first_name},

    Thanks for creating an account with Adverse!

    To verify your email, please click the link below:
    {verification_link}

    If you didn’t create an account, you can safely ignore this email.

    Best regards,
    The Adverse Team
    """
    sendCustomEmail(subject, message, user.email)

def verifyEmail(request, uidb64, token):
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
    if user is not None and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save()
        storage = messages.get_messages(request)
        storage.used = True
        # Log the user in after verification
       # user.backend = 'django.contrib.auth.backends.ModelBackend'
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        messages.success(request, "Your account have been verified.")
        return redirect("admanager:profile") # set for now
    else:
        return render(request, 'security/verification_failed.html')

def verification_pending(request):
    email = request.session.get('pending_verification_email', '')
    return render(request, 'security/verification_pending.html', {'email':email})

#@ratelimit(key='ip', rate='10/h', block=True)
#@ratelimit(key='post:email', rate='3/h', block=True)
#@ratelimit(key='post:email', rate='6/d', block=True)
def resendVerificationLink(request):
    if request.user.is_authenticated and request.user.is_active: 
        messages.info(request, "Your email is already verified.")
        return redirect('security:login')
    if request.method == "POST":
        email = request.POST.get('email', '').strip()
        try:
            validate_email(email)
        except ValidationError:
            messages.error(request, "Please enter a valid email address.")
            return render(request, 'security/resendVerification.html')
        try: 
            user = User.objects.get(email=email)
            if not user.is_active:
                try:
                    sendVerificationEmail(user, request)
                except ValidationError as e: 
                    messages.error(request, str(e))
                    return render(request, 'security/resendVerification.html')
        except User.DoesNotExist:
            pass
        messages.success(request, 'If that email is registered and unverified, a new link has been sent.')
        return redirect('security:verificationpending')
    return render(request, 'security/resendVerification.html') 
  
#@ratelimit(key='ip', rate='10/h', block=True)
#@ratelimit(key='post:email', rate='3/h', block=True)
@transaction.atomic
def registerAccount(request):
    if request.method == "POST": 
        form = RegisterForm(request.POST)
        print("FORM ERRORS:", form.errors) 
        if form.is_valid():
            user = form.save(commit=False)
            user.role = "ad_manager" # set for now
            user.is_active = False 
            user.set_password(form.cleaned_data["password"])
            user.save()
            try: 
                sendVerificationEmail(user, request)
                messages.success(request, "Verification email sent to " + user.email )
                return render(request, "security/verification_pending.html", {"email":user.email})
            except ValidationError as e:
                user.delete() 
                messages.error(request, str(e))
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    if field == "__all__":
                        messages.error(request, error)
                    else:
                        messages.error(request, f"{field.capitalize()}: {error}")
    else:
        form = RegisterForm()
    return render(request, "security/register.html", {"form":form})

#@ratelimit(key='ip', rate='10/m', block=True)
#@ratelimit(key='post:email', rate='5/m', block=True)
def loginAccount(request):
    # Clear any stale messages from other pages (e.g. registration)
    if request.method == "GET":
        storage = messages.get_messages(request)
        storage.used = True

    if request.method == "POST": 
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data.get("email")
            password = form.cleaned_data.get("password")
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                messages.error(request, "Invalid email or password.")
                return render(request, "security/login.html", {"form": form})
            if not user.check_password(password):
                messages.error(request, "Login failed. Please check your credentials and try again.")
                return render(request, "security/login.html", {"form": form})
            if not user.is_active:
                request.session['pending_verification_email'] = user.email
                messages.error(request, "Please verify your email address before logging in.")
                sendVerificationEmail(user, request)
                return redirect('security:verificationpending')
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            remember_me = form.cleaned_data.get("remember_me")
            if remember_me:
                request.session.set_expiry(60 * 60 * 24 * 30)  
            else:
                request.session.set_expiry(0) 
            messages.success(request, f"Welcome back, {user.first_name}")
            return redirect('admanager:dashboard')
    else:
        form = LoginForm()
    return render(request, "security/login.html", {"form": form})

@login_required
def logoutAccount(request):
    if request.method == "POST" or settings.DEBUG: # dev only
        first_name = request.user.first_name  
        storage = messages.get_messages(request)
        storage.used = True
        logout(request)
        messages.success(request, f'{first_name} logged out successfully')
        return redirect("security:login")
    else:
        return redirect("adverse:home")
    
def delayed_send_email(user, request):
    def _send_with_delay():
        time.sleep(random.uniform(1.0, 2.0)) 
        try:
            if user is not None:
                sendPasswordResetLink(user, request)
        except ValidationError:
            pass 
    thread = threading.Thread(target=_send_with_delay)
    thread.daemon = True # in prod use django-Q
    thread.start()

# handle password reset request
def passwordReset(request): 
    if request.method == "POST":
        form = PasswordResetForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            try: 
                user = User.objects.get(email=email)
                delayed_send_email(user, request)
            except User.DoesNotExist: 
                delayed_send_email(None, request)
           # messages.success(request, "If an account with that email exists, a password")
            return redirect("security:passwordresetdone")
    else:
        form = PasswordResetForm()
    return render(request, "security/passwordReset.html", {"form":form})

@require_http_methods(["GET"])
def password_reset_done(request):
    return render(request, 'security/passwordResetDone.html')


def sendPasswordResetLink(user, request):
    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))

    reset_link = request.build_absolute_uri(
        reverse('security:newpasswordReset', kwargs={"uidb64":uid, "token":token})
    )

    subject = "Password Reset"
    message = f"""Hello {user.first_name}
    You requested a password reset for your account. Please click the link below to reset your password:

    {reset_link}

    If you didn't request this, you can safely ignore this email.

    This link will expire in 24 hours.
"""
    sendCustomEmail(subject, message, user.email)

@require_http_methods(["GET", "POST"])
def new_password_request(request, uidb64, token):
    try: 
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
    if user is not None and default_token_generator.check_token(user, token):
        if request.method == "POST":
            form = SetPasswordForm(user, request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, "Your password has been reset successfully. You can now log in with your new password.")
                return redirect("security:login")
        else:
            form = SetPasswordForm(user)
        return render(request, "security/newpassword.html", {"form": form})
    else: 
        messages.error(request, "The password reset link is invalid or has expired.")
        return render(request, "security/passwordresetinvalid.html")

@require_http_methods(["GET"])
def passwordRestComplete(request):
    messages.success(request, "Your password has been reset successfully.")
    return redirect("security:login")

@require_http_methods(['GET', 'POST'])
@ratelimit(key='ip', rate='5/h', method='POST', block=True)
@ratelimit(key='post:email', rate='3/h', method='POST', block=True)
def resend_passwordreset_link(request):
    if request.method == "POST":
        email = request.POST.get('email', '').strip()
        try:
            validate_email(email) 
        except ValidationError:
            messages.error(request, "Please enter a valid email address")
            return render(request, "security/passwordReset.html")
        try:
            user = User.objects.get(email=email)
            delayed_send_email(user, request)
        except User.DoesNotExist:
            delayed_send_email(None, request)

       # messages.success(request, "If an security with that email exists, a password reset link has been sent.")
        return redirect("security:passwordresetdone")
    return render(request, "security/passwordReset.html")

def post_login(request):
    if request.user.is_authenticated:
        if request.user.role:
            if request.user.role == 'ad_manager':
                return redirect('admanager:dashboard')
            else:
                return redirect('adverse:home')
        else:
            return redirect('adverse:home')