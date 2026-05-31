from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import get_user_model
from .models import Admanager
from .forms import AdManagerProfileForm
from security.models import CustomUser
from django.contrib import messages
from functools import wraps
from django.contrib.auth.decorators import login_required
from admanager.decorators import ad_manager_required
User = get_user_model()


# AP
@login_required(login_url='security:login')
@ad_manager_required
def adManagerDashboard(request):
    try:
        ad_manager = request.user.ad_manager
    except Admanager.DoesNotExist:
        messages.error(request, "Ad manager profile not found.")
        return redirect("security:login")  # or redirect to profile setup page

    context = {
        "ad_manager": ad_manager,
        # Main dashboard stats
        "total_billboards": ad_manager.total_billboards,
        "total_campaigns_served": ad_manager.total_campaigns_serverd,
        "total_impressions": ad_manager.total_impressions,
        # Profile/status details
        "business_name": ad_manager.business_name,
        "business_type": ad_manager.business_type,
        "verification_status": ad_manager.verification_status,
        "is_active": ad_manager.is_active,
        "rejection_reason": ad_manager.rejection_reason,
        # Contact/location
        "business_email": ad_manager.business_email,
        "business_phone": ad_manager.business_phone,
        "website": ad_manager.website,
        "address": ad_manager.address,
        "city": ad_manager.city,
        "state": ad_manager.state,
        "country": ad_manager.country,
    }
    return render(request, "adManager/dashboard.html", context)

# create an ad manager profile 
@login_required(login_url='security:login')
def adManagerProfile(request):
    if hasattr(request.user, 'ad_manager'):
        messages.info(request, "Your profile already exists.")
        return redirect("admanager:dashboard")

    if request.method == "POST": 
        form = AdManagerProfileForm(request.POST)
        if form.is_valid(): 
            admanagerProfile =  form.save(commit=False)
            admanagerProfile.user = request.user
            admanagerProfile.save()
            messages.success(request, "Your account has been created!")
            return redirect("admanager:dashboard")
    else: 
        form = AdManagerProfileForm()
    return render(request, "adManager/profile.html", {"form": form}) 

@login_required(login_url='security:login')
@ad_manager_required
def adManager_setting(request):
    admanager = request.user.ad_manager
    return render(request, "adManager/settings.html", {"admanager":admanager})

# edit profile 
@login_required(login_url='security:login')
@ad_manager_required 
def adManagerProfile_settings(request): 
    ad_manager = get_object_or_404(Admanager, user=request.user)
    if request.method == "POST":
        form = AdManagerProfileForm(request.POST, instance=ad_manager)
        if form.is_valid():
            saved_profile = form.save()
            saved_profile.refresh_from_db()
            messages.success(request, 'Profile updated successfully.', extra_tags='profile')
            form = AdManagerProfileForm(instance=ad_manager)
        else: 
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = AdManagerProfileForm(instance=ad_manager)
    return render(request, 'partials/admanager/settingsprofile.html', {'form': form})

