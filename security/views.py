from django.shortcuts import render, redirect
from .forms import RegisterForm, LoginForm, PasswordResetForm, SetPasswordForm
from django.contrib.auth import get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib import messages
from .models import CustomUser
from django_ratelimit.decorators import ratelimit
from django.core.exceptions import ValidationError
from django.conf import settings
from django.core.validators import validate_email
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.db import transaction
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods

from core.services.email_service import ( send_verification_email, send_password_reset_email_safe, send_password_changed_email, )

User = get_user_model()

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
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        messages.success(request, "Your account has been verified.")
        return redirect("security:selectrole")
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
                    send_verification_email(user, request)  
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
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False # until a user is verified 

            #user.first_name = request.POST.get('first_name', '').strip()
            #user.last_name = request.POST.get('last_name', '').strip()
            user.set_password(form.cleaned_data["password"])
            user.save()
            try: 
                send_verification_email(user, request)  
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
                send_verification_email(user, request)  
                return redirect('security:verificationpending')
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            remember_me = form.cleaned_data.get("remember_me")
            if remember_me:
                request.session.set_expiry(60 * 60 * 24 * 30)
            else:
                request.session.set_expiry(0)
            #messages.success(request, f"Welcome back, {user.first_name}")
            if user.role == CustomUser.UserRole.ADVERTISER:
                if hasattr(user, 'advertiser_profile'):
                    return redirect('advertiser:dashboard')
                return redirect('advertiser:create_profile')
            elif user.role == CustomUser.UserRole.ADMIN or user.is_staff:
                return redirect('admin_panel:dashboard')
            else:
                if hasattr(user, 'ad_manager'):
                    #ad_manager = user.ad_manager
                    #ad_manager.revenue = ad_manager.calculate_revenue()
                   # ad_manager.save(update_fields=['revenue'])
                    return redirect('admanager:dashboard')
                return redirect('admanager:profile')
    else:
        form = LoginForm()
    return render(request, "security/login.html", {"form": form})

@login_required
def logoutAccount(request):
    if request.method == "POST" or settings.DEBUG: # dev only
        #first_name = request.user.first_name  
        storage = messages.get_messages(request)
        storage.used = True
        logout(request)
        #messages.success(request, f'{first_name} logged out successfully')
        return redirect("security:login")
    else:
        return redirect("adverse:home")
    
@login_required(login_url='security:login')
def selectuser_role(request):
    # Check if user already has a role selected
    if request.user.role:
        if request.user.role == CustomUser.UserRole.AD_MANAGER:
            messages.info(request, "You have already selected your role as Ad manager.")
            return redirect("adverse:home")
        elif request.user.role == CustomUser.UserRole.ADVERTISER:
            messages.info(request, "You have already selected your role as advertiser.")
            return redirect('advertiser:dashboard') # set for now
    if request.method == "POST":
        role = request.POST.get("role")
        if role in [CustomUser.UserRole.ADVERTISER, CustomUser.UserRole.AD_MANAGER]:
            request.user.role = role
            request.user.save()
        
            if role == CustomUser.UserRole.AD_MANAGER:
                messages.success(request, "Your role has been set to Ad manager, please create a profile")
                return redirect("admanager:profile")
            else:
                messages.success(request, "Your role has been set to Advertiser. Please create a profile.")
                return redirect("advertiser:create_profile")
        else:
            messages.error(request, "Invalid role selected.")
    return render(request, 'security/selectrole.html')

# handle password reset request
def passwordReset(request): 
    if request.method == "POST":
        form = PasswordResetForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            try: 
                user = User.objects.get(email=email)
                send_password_reset_email_safe(user, request)
            except User.DoesNotExist: 
                send_password_reset_email_safe(None, request)
           # messages.success(request, "If an account with that email exists, a password")
            return redirect("security:passwordresetdone")
    else:
        form = PasswordResetForm()
    return render(request, "security/passwordReset.html", {"form":form})

@require_http_methods(["GET"])
def password_reset_done(request):
    return render(request, 'security/passwordResetDone.html')

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
            send_password_reset_email_safe(user, request)
        except User.DoesNotExist:
            send_password_reset_email_safe(None, request)

       # messages.success(request, "If an security with that email exists, a password reset link has been sent.")
        return redirect("security:passwordresetdone")
    return render(request, "security/passwordReset.html")

def post_login(request):
    if request.user.is_authenticated:
        role = request.user.role
        if role == CustomUser.UserRole.ADVERTISER:
            if hasattr(request.user, 'advertiser_profile'):
                return redirect('advertiser:dashboard')
            return redirect('advertiser:create_profile')
        elif role == CustomUser.UserRole.ADMIN or request.user.is_staff:
            return redirect('admin_panel:dashboard')
        elif role == CustomUser.UserRole.AD_MANAGER:
            if hasattr(request.user, 'ad_manager'):
                return redirect('admanager:dashboard')
            return redirect('admanager:profile')
    return redirect('adverse:home')

@login_required(login_url='security:login')
#@ratelimit(key='user', rate='5/h', method='POST', block=True)
def change_password(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            # Notify the user — cheap, high-value: if this wasn't them,
            # this is their only signal that something happened.
            send_password_changed_email(user)
            messages.success(request, 'Your password has been changed successfully.')
            role = request.user.role
            if role == CustomUser.UserRole.ADVERTISER:
                return redirect('advertiser:settings')
            elif role == CustomUser.UserRole.ADMIN or request.user.is_staff:
                return redirect('admin_panel:dashboard')
            else:
                return redirect('admanager:settings')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, error)
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'security/change_password.html', {'form': form})