from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Sum
from django.core.serializers.json import DjangoJSONEncoder
from security.models import CustomUser
from .models import Advertiser, Media, Campaign, CampaignSlot
from .forms import AdvertiserProfileForm, MediaUploadForm, CampaignForm
from .decorators import advertiser_required
from device.models import Billboard
import json


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

    # Detailed State Counts
    draft_campaigns_count = advertiser.campaigns.filter(status=Campaign.Status.DRAFT).count()
    rejected_campaigns_count = advertiser.campaigns.filter(status=Campaign.Status.REJECTED).count()
    completed_campaigns_count = advertiser.campaigns.filter(status=Campaign.Status.COMPLETED).count()

    # Advanced Calculations
    total_active_budget = advertiser.campaigns.filter(
        status__in=[Campaign.Status.ACTIVE, Campaign.Status.APPROVED]
    ).aggregate(total=Sum('budget'))['total'] or 0

    total_lifetime_budget = advertiser.campaigns.exclude(
        status__in=[Campaign.Status.DRAFT, Campaign.Status.CANCELLED]
    ).aggregate(total=Sum('budget'))['total'] or 0

    daily_slots_booked = CampaignSlot.objects.filter(
        campaign__advertiser=advertiser,
        campaign__status=Campaign.Status.ACTIVE
    ).aggregate(total=Sum('slots_per_day'))['total'] or 0

    total_media_size_mb = round(
        (advertiser.media_files.aggregate(total_size=Sum('file_size_bytes'))['total_size'] or 0) / (1024 * 1024), 
        2
    )

    # Calculate Monthly Spend (rolling 12 months) and Annual Spend (last 5 years)
    today = timezone.now().date()
    current_year = today.year
    current_month = today.month

    # Generate rolling 12 months list (tuples of (year, month))
    months_list = []
    for i in range(11, -1, -1):
        m = current_month - i
        y = current_year
        while m <= 0:
            m += 12
            y -= 1
        months_list.append((y, m))

    # Initialize data dict with 0
    from datetime import date
    monthly_data = {}
    for y, m in months_list:
        month_name = date(y, m, 1).strftime("%b %Y")
        monthly_data[month_name] = 0.0

    # Same for annual data (last 5 years)
    years_list = range(today.year - 4, today.year + 1)
    annual_data = {str(y): 0.0 for y in years_list}

    # Retrieve all campaigns for spend aggregation (excluding Draft and Cancelled)
    spend_campaigns = advertiser.campaigns.exclude(
        status__in=[Campaign.Status.DRAFT, Campaign.Status.CANCELLED]
    )

    for campaign in spend_campaigns:
        c_date = campaign.start_date
        if c_date:
            # Monthly rolling accumulation
            c_month_name = c_date.strftime("%b %Y")
            if c_month_name in monthly_data:
                monthly_data[c_month_name] += float(campaign.budget)
            
            # Annual accumulation
            c_year_str = str(c_date.year)
            if c_year_str in annual_data:
                annual_data[c_year_str] += float(campaign.budget)

    # Convert to lists for JSON serialization
    monthly_labels = list(monthly_data.keys())
    monthly_values = list(monthly_data.values())

    annual_labels = list(annual_data.keys())
    annual_values = list(annual_data.values())

    monthly_labels_json = json.dumps(monthly_labels)
    monthly_values_json = json.dumps(monthly_values)
    annual_labels_json = json.dumps(annual_labels)
    annual_values_json = json.dumps(annual_values)

    # Recent Campaigns (last 5)
    recent_campaigns = advertiser.campaigns.order_by('-created_at')[:5]

    return render(request, 'advertiser/dashboard.html', {
        'advertiser': advertiser,
        'media_count': media_count,
        'active_campaigns': active_campaigns,
        'pending_campaigns': pending_campaigns,
        'recent_media': recent_media,
        'recent_campaigns': recent_campaigns,

        # New metrics
        'draft_campaigns_count': draft_campaigns_count,
        'rejected_campaigns_count': rejected_campaigns_count,
        'completed_campaigns_count': completed_campaigns_count,
        'total_active_budget': total_active_budget,
        'total_lifetime_budget': total_lifetime_budget,
        'daily_slots_booked': daily_slots_booked,
        'total_media_size_mb': total_media_size_mb,

        # Chart JSON
        'monthly_labels_json': monthly_labels_json,
        'monthly_values_json': monthly_values_json,
        'annual_labels_json': annual_labels_json,
        'annual_values_json': annual_values_json,
    })


@login_required(login_url='security:login')
@advertiser_required
def browse_billboards(request):
    advertiser = request.user.advertiser_profile
    billboards = Billboard.objects.filter(availability='available')
    
    screen_type = request.GET.get('screen_type', '')
    max_price = request.GET.get('max_price', '')
    country = request.GET.get('country', '').strip()
    state = request.GET.get('state', '').strip()
    location_name = request.GET.get('location_name', '').strip()
    latitude = request.GET.get('latitude', '').strip()
    longitude = request.GET.get('longitude', '').strip()

    if screen_type:
        billboards = billboards.filter(screen_type=screen_type)
    if max_price:
        try:
            billboards = billboards.filter(price_per_slot__lte=float(max_price))
        except ValueError:
            pass

    if country:
        billboards = billboards.filter(country__icontains=country)
    if state:
        billboards = billboards.filter(state__icontains=state)
    if location_name:
        billboards = billboards.filter(location_name__icontains=location_name)

    if latitude and longitude:
        try:
            lat = float(latitude)
            lng = float(longitude)
            billboards = billboards.filter(
                latitude__gte=lat - 0.1, latitude__lte=lat + 0.1,
                longitude__gte=lng - 0.1, longitude__lte=lng + 0.1
            )
        except ValueError:
            pass

    return render(request, 'advertiser/billboard_browse.html', {
        'advertiser': advertiser,
        'billboards': billboards,
        'screen_type': screen_type,
        'max_price': max_price,
        'country': country,
        'state': state,
        'location_name': location_name,
        'latitude': latitude,
        'longitude': longitude,
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

    # Build billboard data map for live JS price calculator
    available_billboards = Billboard.objects.filter(availability='available')
    billboards_data = {
        str(bb.pk): {
            'name': bb.name,
            'location': bb.location_name,
            'state': bb.state,
            'country': bb.country,
            'price': float(bb.price_per_slot),
            'charge_unit': bb.charge_unit,
            'screen_type': bb.get_screen_type_display(),
            'hours_start': str(bb.operating_hours_start),
            'hours_end': str(bb.operating_hours_end),
            'media_url': bb.media_file.url if bb.media_file else None,
            'media_is_video': bool(bb.media_file and any(
                str(bb.media_file.name).lower().endswith(ext)
                for ext in ['.mp4', '.mov', '.webm', '.m4v']
            )),
        }
        for bb in available_billboards
    }

    # Pre-select billboard if coming from the Book button
    preselected_pk = request.GET.get('billboard', '')

    if request.method == 'POST':
        form = CampaignForm(request.POST, advertiser=advertiser)
        if form.is_valid():
            campaign = form.save(commit=False)
            campaign.advertiser = advertiser
            try:
                campaign.save()
                # Create CampaignSlot for the selected billboard
                slots_per_day = form.cleaned_data.get('slots_per_day', 1)
                billboard = form.cleaned_data['billboard']
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
        initial = {}
        if preselected_pk:
            try:
                bb = Billboard.objects.get(pk=preselected_pk, availability='available')
                initial['billboard'] = bb
            except Billboard.DoesNotExist:
                pass
        form = CampaignForm(advertiser=advertiser, initial=initial)

    return render(request, 'advertiser/campaign_create.html', {
        'advertiser': advertiser,
        'form': form,
        'preselected_pk': preselected_pk,
        'billboards_json': json.dumps(billboards_data, cls=DjangoJSONEncoder),
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

    # Always sync the estimated price on GET so the template shows
    # the live calculated figure (not a stale value from creation time)
    if campaign.status in [Campaign.Status.DRAFT, Campaign.Status.REJECTED]:
        campaign.sync_estimated_price()

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
    first_billboard = existing_slots.first().billboard if existing_slots.exists() else None

    # Build billboard data for JS calculator
    available_billboards = Billboard.objects.filter(availability='available')
    billboards_data = {
        str(bb.pk): {
            'name': bb.name,
            'location': bb.location_name,
            'state': bb.state,
            'country': bb.country,
            'price': float(bb.price_per_slot),
            'charge_unit': bb.charge_unit,
            'screen_type': bb.get_screen_type_display(),
            'hours_start': str(bb.operating_hours_start),
            'hours_end': str(bb.operating_hours_end),
            'media_url': bb.media_file.url if bb.media_file else None,
            'media_is_video': bool(bb.media_file and any(
                str(bb.media_file.name).lower().endswith(ext)
                for ext in ['.mp4', '.mov', '.webm', '.m4v']
            )),
        }
        for bb in available_billboards
    }

    if request.method == 'POST':
        form = CampaignForm(request.POST, instance=campaign, advertiser=advertiser)
        if form.is_valid():
            try:
                form.save()
                slots_per_day = form.cleaned_data.get('slots_per_day', 1)
                campaign.campaign_slots.all().delete()
                billboard = form.cleaned_data['billboard']
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
                'billboard': first_billboard,
                'slots_per_day': initial_slots_per_day,
            }
        )
    return render(request, 'advertiser/campaign_edit.html', {
        'advertiser': advertiser,
        'campaign': campaign,
        'form': form,
        'billboards_json': json.dumps(billboards_data, cls=DjangoJSONEncoder),
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
