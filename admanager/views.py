from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import get_user_model
from .models import Admanager
from .forms import AdManagerProfileForm, BillboardForm
from device.models import Billboard
from advertiser.models import Campaign
from security.models import CustomUser
from django.contrib import messages
from functools import wraps
from django.contrib.auth.decorators import login_required
from admanager.decorators import ad_manager_required
from django.core.exceptions import ValidationError
from django.utils import timezone
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


@login_required(login_url='security:login')
@ad_manager_required
def billboard_list(request):
    ad_manager = request.user.ad_manager
    billboards = Billboard.objects.filter(ad_manager=ad_manager).order_by('-created_at')
    return render(request, 'adManager/billboard_list.html', {
        'ad_manager': ad_manager,
        'billboards': billboards,
    })


@login_required(login_url='security:login')
@ad_manager_required
def billboard_create(request):
    ad_manager = request.user.ad_manager
    if request.method == 'POST':
        form = BillboardForm(request.POST)
        if form.is_valid():
            billboard = form.save(commit=False)
            billboard.ad_manager = ad_manager
            billboard.save()
            messages.success(request, 'Billboard added successfully.')
            return redirect('admanager:billboard_list')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field.replace('_', ' ').title()}: {error}")
    else:
        form = BillboardForm()
    return render(request, 'adManager/billboard_form.html', {
        'ad_manager': ad_manager,
        'form': form,
        'action': 'Add',
    })


@login_required(login_url='security:login')
@ad_manager_required
def billboard_edit(request, pk):
    ad_manager = request.user.ad_manager
    billboard = get_object_or_404(Billboard, pk=pk, ad_manager=ad_manager)
    if request.method == 'POST':
        form = BillboardForm(request.POST, instance=billboard)
        if form.is_valid():
            form.save()
            messages.success(request, 'Billboard updated successfully.')
            return redirect('admanager:billboard_list')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field.replace('_', ' ').title()}: {error}")
    else:
        form = BillboardForm(instance=billboard)
    return render(request, 'adManager/billboard_form.html', {
        'ad_manager': ad_manager,
        'form': form,
        'action': 'Edit',
        'billboard': billboard,
    })


@login_required(login_url='security:login')
@ad_manager_required
def campaign_requests(request):
    ad_manager = request.user.ad_manager
    campaigns = Campaign.objects.filter(
        campaign_slots__billboard__ad_manager=ad_manager,
        status=Campaign.Status.PENDING_MANAGER_REVIEW,
    ).distinct().select_related('advertiser', 'media').order_by('-updated_at')
    return render(request, 'adManager/campaign_requests.html', {
        'ad_manager': ad_manager,
        'campaigns': campaigns,
    })


@login_required(login_url='security:login')
@ad_manager_required
def campaign_request_detail(request, pk):
    ad_manager = request.user.ad_manager
    campaign = get_object_or_404(
        Campaign,
        pk=pk,
        campaign_slots__billboard__ad_manager=ad_manager,
        status=Campaign.Status.PENDING_MANAGER_REVIEW,
    )
    if request.method == 'POST':
        action = request.POST.get('action')
        reason = request.POST.get('reason', '').strip()
        try:
            if action == 'approve':
                campaign.manager_approve(request.user)
                messages.success(request, 'Campaign approved. Media is now fully live.')
                return redirect('admanager:campaign_requests')
            elif action == 'reject':
                campaign.reject(request.user, reason)
                messages.success(request, 'Campaign rejected.')
                return redirect('admanager:campaign_requests')
        except ValidationError as e:
            messages.error(request, str(e))
    slots = campaign.campaign_slots.select_related('billboard').all()
    return render(request, 'adManager/campaign_request_detail.html', {
        'ad_manager': ad_manager,
        'campaign': campaign,
        'slots': slots,
    })


@login_required(login_url='security:login')
@ad_manager_required
def request_verification(request):
    if request.method == 'POST':
        ad_manager = request.user.ad_manager
        if ad_manager.verification_status == 'pending' and not ad_manager.verification_requested:
            ad_manager.verification_requested = True
            ad_manager.verification_requested_at = timezone.now()
            ad_manager.save(update_fields=['verification_requested', 'verification_requested_at'])
            messages.success(request, 'Verification request submitted. An admin will review your account.')
    return redirect('admanager:dashboard')

