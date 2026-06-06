from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Count
from .decorators import admin_required
from advertiser.models import Advertiser, Media, Campaign
from admanager.models import Admanager
from device.models import Billboard, PlayerDevice


@login_required(login_url='security:login')
@admin_required
def admin_dashboard(request):
    pending_advertisers = Advertiser.objects.filter(is_verified=False).count()
    pending_media = Media.objects.filter(status=Media.Status.PENDING).count()
    pending_campaigns = Campaign.objects.filter(status=Campaign.Status.PENDING_ADMIN_REVIEW).count()
    pending_ad_managers = Admanager.objects.filter(
        verification_status=Admanager.VerificationStatus.PENDING,
        verification_requested=True,
    ).count()

    # Extra KPIs
    total_advertisers = Advertiser.objects.count()
    total_ad_managers = Admanager.objects.count()
    active_campaigns = Campaign.objects.filter(status=Campaign.Status.ACTIVE).count()
    total_billboards = Billboard.objects.count()

    # Devices counts
    total_devices = PlayerDevice.objects.count()
    five_minutes_ago = timezone.now() - timezone.timedelta(minutes=5)
    online_devices = PlayerDevice.objects.filter(
        last_seen_at__gte=five_minutes_ago,
        status=PlayerDevice.Status.ACTIVE
    ).count()

    # Recent pending submissions
    recent_advertisers = Advertiser.objects.select_related('user').filter(is_verified=False).order_by('-created_at')[:5]
    recent_ad_managers = Admanager.objects.select_related('user').filter(
        verification_status=Admanager.VerificationStatus.PENDING,
        verification_requested=True,
    ).order_by('-verification_requested_at')[:5]
    recent_media = Media.objects.select_related('advertiser').filter(status=Media.Status.PENDING).order_by('-created_at')[:5]
    recent_campaigns = Campaign.objects.select_related('advertiser', 'media').filter(status=Campaign.Status.PENDING_ADMIN_REVIEW).order_by('-created_at')[:5]

    return render(request, 'admin_panel/dashboard.html', {
        'pending_advertisers': pending_advertisers,
        'pending_ad_managers': pending_ad_managers,
        'pending_media': pending_media,
        'pending_campaigns': pending_campaigns,

        'total_advertisers': total_advertisers,
        'total_ad_managers': total_ad_managers,
        'active_campaigns': active_campaigns,
        'total_billboards': total_billboards,
        'total_devices': total_devices,
        'online_devices': online_devices,

        'recent_advertisers': recent_advertisers,
        'recent_ad_managers': recent_ad_managers,
        'recent_media': recent_media,
        'recent_campaigns': recent_campaigns,
    })


@login_required(login_url='security:login')
@admin_required
def advertiser_list(request):
    advertisers = Advertiser.objects.select_related('user')\
        .annotate(
            media_count=Count('media_files', distinct=True),
            campaign_count=Count('campaigns', distinct=True)
        )\
        .order_by('is_verified', '-verification_requested', '-verification_requested_at')
    if request.method == 'POST':
        pk = request.POST.get('pk')
        action = request.POST.get('action')
        advertiser = get_object_or_404(Advertiser, pk=pk)
        if action == 'verify':
            advertiser.verify(request.user)
            messages.success(request, f'{advertiser.business_name} verified.')
        elif action == 'suspend':
            advertiser.is_verified = False
            advertiser.save(update_fields=['is_verified'])
            messages.success(request, f'{advertiser.business_name} suspended.')
        return redirect('admin_panel:advertiser_list')
    return render(request, 'admin_panel/advertisers.html', {'advertisers': advertisers})


@login_required(login_url='security:login')
@admin_required
def media_review_list(request):
    media_files = Media.objects.filter(status=Media.Status.PENDING).select_related('advertiser').order_by('created_at')
    if request.method == 'POST':
        pk = request.POST.get('pk')
        action = request.POST.get('action')
        reason = request.POST.get('reason', '').strip()
        media = get_object_or_404(Media, pk=pk)
        try:
            if action == 'approve':
                media.approve(request.user)
                messages.success(request, f'"{media.title}" approved.')
            elif action == 'reject':
                media.reject(request.user, reason)
                messages.success(request, f'"{media.title}" rejected.')
        except ValidationError as e:
            messages.error(request, str(e))
        return redirect('admin_panel:media_review')
    return render(request, 'admin_panel/media.html', {'media_files': media_files})


@login_required(login_url='security:login')
@admin_required
def campaign_review_list(request):
    campaigns = Campaign.objects.filter(
        status=Campaign.Status.PENDING_ADMIN_REVIEW
    ).select_related('advertiser', 'media').order_by('created_at')
    return render(request, 'admin_panel/campaigns.html', {'campaigns': campaigns})


@login_required(login_url='security:login')
@admin_required
def admin_campaign_detail(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk, status=Campaign.Status.PENDING_ADMIN_REVIEW)
    if request.method == 'POST':
        action = request.POST.get('action')
        reason = request.POST.get('reason', '').strip()
        try:
            if action == 'forward':
                campaign.admin_forward_to_manager(request.user)
                messages.success(request, 'Campaign forwarded to Ad Manager for review.')
                return redirect('admin_panel:campaign_review')
            elif action == 'reject':
                campaign.reject(request.user, reason)
                messages.success(request, 'Campaign rejected.')
                return redirect('admin_panel:campaign_review')
        except ValidationError as e:
            messages.error(request, str(e))
    slots = campaign.campaign_slots.select_related('billboard').all()
    return render(request, 'admin_panel/campaign_detail.html', {
        'campaign': campaign,
        'slots': slots,
    })


@login_required(login_url='security:login')
@admin_required
def ad_manager_list(request):
    ad_managers = Admanager.objects.select_related('user', 'verified_by')\
        .annotate(billboard_count=Count('billboards', distinct=True))\
        .order_by('-verification_requested', '-verification_requested_at', '-created_at')
    if request.method == 'POST':
        pk = request.POST.get('pk')
        action = request.POST.get('action')
        reason = request.POST.get('reason', '').strip()
        ad_manager = get_object_or_404(Admanager, pk=pk)
        if action == 'verify':
            ad_manager.verify(request.user)
            messages.success(request, f'{ad_manager.business_name} verified.')
        elif action == 'reject':
            ad_manager.reject(request.user, reason)
            messages.success(request, f'{ad_manager.business_name} rejected.')
        elif action == 'suspend':
            ad_manager.suspend()
            messages.success(request, f'{ad_manager.business_name} suspended.')
        return redirect('admin_panel:ad_manager_list')
    return render(request, 'admin_panel/ad_managers.html', {'ad_managers': ad_managers})
