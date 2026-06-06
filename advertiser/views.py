from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils import timezone
from security.models import CustomUser
from .models import Advertiser, Media, Campaign, CampaignSlot
from .forms import AdvertiserProfileForm, MediaUploadForm, CampaignForm
from .decorators import advertiser_required
from device.models import Billboard


@login_required(login_url='security:login')
def create_advertiser_profile(request):
    if request.user.role != CustomUser.UserRole.ADVERTISER:
        return redirect('adverse:home')
    if hasattr(request.user, 'advertiser_profile'):
        return redirect('advertiser:dashboard')
    if request.method == 'POST':
        form = AdvertiserProfileForm(request.POST)
        if form.is_valid():
            profile = form.save(commit=False)
            profile.user = request.user
            profile.save()
            messages.success(request, 'Profile created! Welcome to Adverse.')
            return redirect('advertiser:dashboard')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field.replace('_', ' ').title()}: {error}")
    else:
        form = AdvertiserProfileForm()
    return render(request, 'advertiser/profile.html', {'form': form})


@login_required(login_url='security:login')
@advertiser_required
def advertiser_dashboard(request):
    advertiser = request.user.advertiser_profile
    media_count = advertiser.media_files.count()
    active_campaigns = advertiser.campaigns.filter(status__in=['active', 'approved']).count()
    pending_campaigns = advertiser.campaigns.filter(
        status__in=['pending_admin_review', 'pending_manager_review']
    ).count()
    recent_media = advertiser.media_files.order_by('-created_at')[:4]
    return render(request, 'advertiser/dashboard.html', {
        'advertiser': advertiser,
        'media_count': media_count,
        'active_campaigns': active_campaigns,
        'pending_campaigns': pending_campaigns,
        'recent_media': recent_media,
    })


@login_required(login_url='security:login')
@advertiser_required
def browse_billboards(request):
    advertiser = request.user.advertiser_profile
    billboards = Billboard.objects.filter(availability='available')
    screen_type = request.GET.get('screen_type', '')
    max_price = request.GET.get('max_price', '')
    if screen_type:
        billboards = billboards.filter(screen_type=screen_type)
    if max_price:
        try:
            billboards = billboards.filter(price_per_slot__lte=float(max_price))
        except ValueError:
            pass
    return render(request, 'advertiser/billboard_browse.html', {
        'advertiser': advertiser,
        'billboards': billboards,
        'screen_type': screen_type,
        'max_price': max_price,
        'screen_type_choices': Billboard.ScreenType.choices,
    })


@login_required(login_url='security:login')
@advertiser_required
def media_library(request):
    advertiser = request.user.advertiser_profile
    media_files = advertiser.media_files.order_by('-created_at')
    return render(request, 'advertiser/media_list.html', {
        'advertiser': advertiser,
        'media_files': media_files,
    })


@login_required(login_url='security:login')
@advertiser_required
def upload_media(request):
    advertiser = request.user.advertiser_profile
    if request.method == 'POST':
        form = MediaUploadForm(request.POST, request.FILES)
        if form.is_valid():
            media = form.save(commit=False)
            media.advertiser = advertiser
            try:
                media.save()
                messages.success(request, 'Media uploaded and pending review.')
                return redirect('advertiser:media_library')
            except ValidationError as e:
                for field, errs in e.message_dict.items():
                    for err in errs:
                        messages.error(request, err)
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field.replace('_', ' ').title()}: {error}")
    else:
        form = MediaUploadForm()
    return render(request, 'advertiser/media_upload.html', {
        'advertiser': advertiser,
        'form': form,
    })


@login_required(login_url='security:login')
@advertiser_required
def campaign_list(request):
    advertiser = request.user.advertiser_profile
    campaigns = advertiser.campaigns.order_by('-created_at')
    return render(request, 'advertiser/campaign_list.html', {
        'advertiser': advertiser,
        'campaigns': campaigns,
    })


@login_required(login_url='security:login')
@advertiser_required
def campaign_create(request):
    advertiser = request.user.advertiser_profile
    if request.method == 'POST':
        form = CampaignForm(request.POST, advertiser=advertiser)
        if form.is_valid():
            campaign = form.save(commit=False)
            campaign.advertiser = advertiser
            try:
                campaign.save()
                # Create CampaignSlots for each selected billboard
                slots_per_day = form.cleaned_data.get('slots_per_day', 1)
                for billboard in form.cleaned_data['billboards']:
                    CampaignSlot.objects.create(
                        campaign=campaign,
                        billboard=billboard,
                        slots_per_day=slots_per_day,
                    )
                messages.success(request, 'Campaign created as draft. Submit it when ready.')
                return redirect('advertiser:campaign_detail', pk=campaign.pk)
            except ValidationError as e:
                for field, errs in e.message_dict.items():
                    for err in errs:
                        messages.error(request, err)
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field.replace('_', ' ').title()}: {error}")
    else:
        form = CampaignForm(advertiser=advertiser)
    return render(request, 'advertiser/campaign_create.html', {
        'advertiser': advertiser,
        'form': form,
    })


@login_required(login_url='security:login')
@advertiser_required
def campaign_detail(request, pk):
    advertiser = request.user.advertiser_profile
    campaign = get_object_or_404(Campaign, pk=pk, advertiser=advertiser)
    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            if action == 'submit':
                campaign.submit_for_approval()
                messages.success(request, 'Campaign submitted for review.')
            elif action == 'cancel':
                campaign.cancel()
                messages.success(request, 'Campaign cancelled.')
        except ValidationError as e:
            messages.error(request, str(e))
        return redirect('advertiser:campaign_detail', pk=campaign.pk)
    slots = campaign.campaign_slots.select_related('billboard').all()
    return render(request, 'advertiser/campaign_detail.html', {
        'advertiser': advertiser,
        'campaign': campaign,
        'slots': slots,
    })


@login_required(login_url='security:login')
@advertiser_required
def campaign_edit(request, pk):
    advertiser = request.user.advertiser_profile
    campaign = get_object_or_404(Campaign, pk=pk, advertiser=advertiser)

    if campaign.status not in [Campaign.Status.DRAFT, Campaign.Status.REJECTED]:
        messages.error(request, 'Only draft or rejected campaigns can be edited.')
        return redirect('advertiser:campaign_detail', pk=campaign.pk)

    existing_slots = campaign.campaign_slots.select_related('billboard').all()
    initial_slots_per_day = existing_slots.first().slots_per_day if existing_slots.exists() else 1

    if request.method == 'POST':
        form = CampaignForm(request.POST, instance=campaign, advertiser=advertiser)
        if form.is_valid():
            try:
                form.save()
                slots_per_day = form.cleaned_data.get('slots_per_day', 1)
                campaign.campaign_slots.all().delete()
                for billboard in form.cleaned_data['billboards']:
                    CampaignSlot.objects.create(
                        campaign=campaign,
                        billboard=billboard,
                        slots_per_day=slots_per_day,
                    )
                messages.success(request, 'Campaign updated.')
                return redirect('advertiser:campaign_detail', pk=campaign.pk)
            except ValidationError as e:
                for field, errs in e.message_dict.items():
                    for err in errs:
                        messages.error(request, err)
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field.replace('_', ' ').title()}: {error}")
    else:
        form = CampaignForm(
            instance=campaign,
            advertiser=advertiser,
            initial={
                'billboards': [str(slot.billboard_id) for slot in existing_slots],
                'slots_per_day': initial_slots_per_day,
            }
        )
    return render(request, 'advertiser/campaign_edit.html', {
        'advertiser': advertiser,
        'campaign': campaign,
        'form': form,
    })


@login_required(login_url='security:login')
@advertiser_required
def advertiser_settings(request):
    advertiser = request.user.advertiser_profile
    if request.method == 'POST':
        form = AdvertiserProfileForm(request.POST, instance=advertiser)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated.')
            return redirect('advertiser:settings')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field.replace('_', ' ').title()}: {error}")
    else:
        form = AdvertiserProfileForm(instance=advertiser)
    return render(request, 'advertiser/settings.html', {
        'advertiser': advertiser,
        'form': form,
    })


@login_required(login_url='security:login')
@advertiser_required
def request_verification(request):
    if request.method == 'POST':
        advertiser = request.user.advertiser_profile
        if not advertiser.is_verified and not advertiser.verification_requested:
            advertiser.verification_requested = True
            advertiser.verification_requested_at = timezone.now()
            advertiser.save(update_fields=['verification_requested', 'verification_requested_at'])
            messages.success(request, 'Verification request submitted. An admin will review your account.')
    return redirect('advertiser:dashboard')
