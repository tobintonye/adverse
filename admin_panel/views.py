from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import Count, Sum
from .decorators import admin_required
from advertiser.models import Advertiser, Media, Campaign, CampaignSlot
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

    # Advanced Calculations
    total_booked_revenue = Campaign.objects.filter(
        status__in=[Campaign.Status.ACTIVE, Campaign.Status.APPROVED]
    ).aggregate(total=Sum('estimated_price'))['total'] or 0

    total_media_size_mb = round(
        (Media.objects.aggregate(total_size=Sum('file_size_bytes'))['total_size'] or 0) / (1024 * 1024), 
        2
    )

    daily_slots_booked = CampaignSlot.objects.filter(
        campaign__status=Campaign.Status.ACTIVE
    ).aggregate(total=Sum('slots_per_day'))['total'] or 0

    # Devices counts
    total_devices = PlayerDevice.objects.count()
    five_minutes_ago = timezone.now() - timezone.timedelta(minutes=5)
    online_devices = PlayerDevice.objects.filter(
        last_seen_at__gte=five_minutes_ago,
        status=PlayerDevice.Status.ACTIVE
    ).count()
    offline_devices = total_devices - online_devices
    device_online_ratio = round((online_devices / total_devices * 100), 1) if total_devices > 0 else 0

    # Recent pending submissions
    recent_advertisers = Advertiser.objects.select_related('user').filter(is_verified=False).order_by('-created_at')[:5]
    recent_ad_managers = Admanager.objects.select_related('user').filter(
        verification_status=Admanager.VerificationStatus.PENDING,
        verification_requested=True,
    ).order_by('-verification_requested_at')[:5]
    recent_media = Media.objects.select_related('advertiser').filter(status=Media.Status.PENDING).order_by('-created_at')[:5]
    recent_campaigns = Campaign.objects.select_related('advertiser', 'media').filter(status=Campaign.Status.PENDING_ADMIN_REVIEW).order_by('-created_at')[:5]

    # Analytics queries: Monthly & Annual campaign runs
    current_year = timezone.now().year
    from django.db.models.functions import ExtractMonth, ExtractYear
    
    monthly_data = Campaign.objects.filter(
        start_date__year=current_year,
        status__in=[Campaign.Status.APPROVED, Campaign.Status.ACTIVE, Campaign.Status.COMPLETED]
    ).annotate(month=ExtractMonth('start_date'))\
     .values('month')\
     .annotate(count=Count('id'))\
     .order_by('month')

    monthly_counts = [0] * 12
    for item in monthly_data:
        m_idx = item['month'] - 1
        if 0 <= m_idx < 12:
            monthly_counts[m_idx] = item['count']

    years_range = list(range(current_year - 4, current_year + 1))
    annual_data = Campaign.objects.filter(
        start_date__year__in=years_range,
        status__in=[Campaign.Status.APPROVED, Campaign.Status.ACTIVE, Campaign.Status.COMPLETED]
    ).annotate(year=ExtractYear('start_date'))\
     .values('year')\
     .annotate(count=Count('id'))\
     .order_by('year')

    annual_counts = {yr: 0 for yr in years_range}
    for item in annual_data:
        yr = item['year']
        if yr in annual_counts:
            annual_counts[yr] = item['count']
    annual_counts_list = [annual_counts[yr] for yr in years_range]

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
        'offline_devices': offline_devices,
        'device_online_ratio': device_online_ratio,
        'total_booked_revenue': total_booked_revenue,
        'total_media_size_mb': total_media_size_mb,
        'daily_slots_booked': daily_slots_booked,

        'recent_advertisers': recent_advertisers,
        'recent_ad_managers': recent_ad_managers,
        'recent_media': recent_media,
        'recent_campaigns': recent_campaigns,
        
        'monthly_counts': monthly_counts,
        'years_range': years_range,
        'annual_counts_list': annual_counts_list,
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
    from django.db.models import Case, When, Value, IntegerField
    media_files = Media.objects.annotate(
        priority=Case(
            When(status=Media.Status.PENDING, then=Value(1)),
            default=Value(2),
            output_field=IntegerField()
        )
    ).select_related('advertiser').order_by('priority', '-created_at')

    if request.method == 'POST':
        pk = request.POST.get('pk')
        action = request.POST.get('action')
        reason = request.POST.get('reason', '').strip()
        media = get_object_or_404(Media, pk=pk)
        
        if media.status != Media.Status.PENDING:
            messages.error(request, f'"{media.title}" has already been processed.')
            return redirect('admin_panel:media_review')

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
    from django.db.models import Case, When, Value, IntegerField
    campaigns = Campaign.objects.exclude(
        status=Campaign.Status.DRAFT
    ).annotate(
        priority=Case(
            When(status=Campaign.Status.PENDING_ADMIN_REVIEW, then=Value(1)),
            default=Value(2),
            output_field=IntegerField()
        )
    ).select_related('advertiser', 'media').order_by('priority', '-created_at')
    return render(request, 'admin_panel/campaigns.html', {'campaigns': campaigns})


@login_required(login_url='security:login')
@admin_required
def admin_campaign_detail(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    if campaign.status == Campaign.Status.DRAFT:
        return redirect('admin_panel:campaign_review')

    if request.method == 'POST':
        if campaign.status != Campaign.Status.PENDING_ADMIN_REVIEW:
            messages.error(request, 'This campaign has already been processed.')
            return redirect('admin_panel:admin_campaign_detail', pk=pk)

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
    from django.db.models import Count, Q
    ad_managers = Admanager.objects.select_related('user', 'verified_by')\
        .annotate(
            billboard_count=Count('billboards', distinct=True),
            campaigns_served_count=Count(
                'billboards__campaign_slots__campaign',
                filter=Q(billboards__campaign_slots__campaign__status__in=[
                    Campaign.Status.APPROVED,
                    Campaign.Status.ACTIVE,
                    Campaign.Status.COMPLETED
                ]),
                distinct=True
            )
        )\
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


@login_required(login_url='security:login')
@admin_required
def revenue_settings(request):
    from decimal import Decimal
    from .models import RevenueSetting
    setting = RevenueSetting.objects.first()
    if not setting:
        setting = RevenueSetting.objects.create(admin_percentage=Decimal('30.00'), admanager_percentage=Decimal('70.00'))

    if request.method == 'POST':
        admin_pct = request.POST.get('admin_percentage')
        admanager_pct = request.POST.get('admanager_percentage')
        try:
            setting.admin_percentage = Decimal(admin_pct)
            setting.admanager_percentage = Decimal(admanager_pct)
            setting.full_clean()
            setting.save()
            messages.success(request, "Revenue split settings updated successfully.")
            return redirect('admin_panel:revenue_settings')
        except (ValueError, ValidationError) as e:
            # Check if validation error has standard dict form or string list
            err_msg = str(e)
            if hasattr(e, 'message_dict') and '__all__' in e.message_dict:
                err_msg = e.message_dict['__all__'][0]
            messages.error(request, f"Error updating settings: {err_msg}")

    return render(request, 'admin_panel/revenue_settings.html', {'setting': setting})


@login_required(login_url='security:login')
@admin_required
def admin_withdrawal_list(request):
    from admanager.models import WithdrawalRequest
    
    if request.method == 'POST':
        pk = request.POST.get('pk')
        action = request.POST.get('action')
        admin_notes = request.POST.get('admin_notes', '').strip()
        
        withdrawal = get_object_or_404(WithdrawalRequest, pk=pk)
        if withdrawal.status != WithdrawalRequest.Status.PENDING:
            messages.error(request, "This withdrawal request has already been processed.")
        else:
            if action == 'approve':
                withdrawal.status = WithdrawalRequest.Status.APPROVED
                withdrawal.admin_notes = admin_notes
                withdrawal.save()
                messages.success(request, f"Withdrawal request of ₦{withdrawal.amount:,.2f} for {withdrawal.ad_manager.business_name} approved.")
            elif action == 'reject':
                withdrawal.status = WithdrawalRequest.Status.REJECTED
                withdrawal.admin_notes = admin_notes
                withdrawal.save()
                messages.warning(request, f"Withdrawal request of ₦{withdrawal.amount:,.2f} for {withdrawal.ad_manager.business_name} rejected.")
        return redirect('admin_panel:withdrawal_list')

    withdrawals = WithdrawalRequest.objects.select_related('ad_manager').order_by('-created_at')
    return render(request, 'admin_panel/withdrawals.html', {'withdrawals': withdrawals})


@login_required(login_url='security:login')
@admin_required
def message_inbox(request):
    from adverse.models import Message
    messages_list = Message.objects.all().order_by('-created_at')
    selected_message = None
    selected_id = request.GET.get('id')
    
    if selected_id:
        selected_message = get_object_or_404(Message, pk=selected_id)
        if not selected_message.is_read:
            selected_message.is_read = True
            selected_message.save(update_fields=['is_read'])
            
    return render(request, 'admin_panel/messages.html', {
        'messages_list': messages_list,
        'selected_message': selected_message,
    })



