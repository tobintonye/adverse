from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import get_user_model
from django.db import models
from .models import Admanager, BankAccount, WithdrawalRequest
from .forms import AdManagerProfileForm, BillboardForm, BankAccountForm
from device.models import Billboard
from advertiser.models import Campaign, CampaignSlot
from security.models import CustomUser
from django.contrib import messages
from functools import wraps
from django.contrib.auth.decorators import login_required
from admanager.decorators import ad_manager_required
from django.core.exceptions import ValidationError
from django.utils import timezone
import json
from datetime import date
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

    # Query campaigns pending this manager's review
    pending_requests_count = Campaign.objects.filter(
        campaign_slots__billboard__ad_manager=ad_manager,
        status=Campaign.Status.PENDING_MANAGER_REVIEW
    ).distinct().count()

    # Calculate Monthly Revenue (rolling 12 months) and Annual Revenue (last 5 years)
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
    monthly_data = {}
    for y, m in months_list:
        month_name = date(y, m, 1).strftime("%b %Y")
        monthly_data[month_name] = 0.0

    # Same for annual data (last 5 years)
    years_list = range(today.year - 4, today.year + 1)
    annual_data = {str(y): 0.0 for y in years_list}

    # Query all active/approved/completed slots booking this manager's billboards
    revenue_slots = CampaignSlot.objects.filter(
        billboard__ad_manager=ad_manager,
        campaign__status__in=[Campaign.Status.APPROVED, Campaign.Status.ACTIVE, Campaign.Status.COMPLETED]
    ).select_related('billboard', 'campaign')

    for slot in revenue_slots:
        c_date = slot.campaign.start_date
        if c_date:
            price = float(slot.slot_price)
            # Monthly rolling accumulation
            c_month_name = c_date.strftime("%b %Y")
            if c_month_name in monthly_data:
                monthly_data[c_month_name] += price
            
            # Annual accumulation
            c_year_str = str(c_date.year)
            if c_year_str in annual_data:
                annual_data[c_year_str] += price

    # Convert to lists for JSON serialization
    monthly_labels_json = json.dumps(list(monthly_data.keys()))
    monthly_values_json = json.dumps(list(monthly_data.values()))
    annual_labels_json = json.dumps(list(annual_data.keys()))
    annual_values_json = json.dumps(list(annual_data.values()))

    context = {
        "ad_manager": ad_manager,
        # Main dashboard stats
        "total_billboards": ad_manager.billboards.count(),
        "total_campaigns_served": ad_manager.received_campaigns.filter(
            status__in=[Campaign.Status.APPROVED, Campaign.Status.ACTIVE, Campaign.Status.COMPLETED]
        ).count(),
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
        # Action alerts
        "pending_requests_count": pending_requests_count,
        # Chart data JSON
        "monthly_labels_json": monthly_labels_json,
        "monthly_values_json": monthly_values_json,
        "annual_labels_json": annual_labels_json,
        "annual_values_json": annual_values_json,
        # Financial stats
        "revenue": ad_manager.revenue,
        "total_withdrawn": ad_manager.total_withdrawn,
        "pending_withdrawal": ad_manager.pending_withdrawal,
        "available_balance": ad_manager.available_balance,
        # Bank account alert
        "has_bank_account": ad_manager.bank_accounts.exists(),
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
    ad_manager = request.user.ad_manager
    active_tab = request.GET.get('tab', 'business')

    # Business Info form
    if request.method == 'POST' and 'save_business' in request.POST:
        form = AdManagerProfileForm(request.POST, instance=ad_manager)
        if form.is_valid():
            form.save()
            messages.success(request, 'Business information updated successfully.')
            return redirect(f"{request.path}?tab=business")
        else:
            active_tab = 'business'
    else:
        form = AdManagerProfileForm(instance=ad_manager)

    bank_accounts = ad_manager.bank_accounts.all()
    bank_form = BankAccountForm()

    return render(request, "adManager/settings.html", {
        "admanager": ad_manager,
        "form": form,
        "bank_accounts": bank_accounts,
        "bank_form": bank_form,
        "active_tab": active_tab,
    })

# edit profile (legacy HTMX partial — kept for backwards compatibility)
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


# ── Bank Account Management ──────────────────────────────────────────────────

@login_required(login_url='security:login')
@ad_manager_required
def bank_account_add(request):
    if request.method != 'POST':
        return redirect('admanager:settings')
    ad_manager = request.user.ad_manager
    if ad_manager.bank_accounts.count() >= 2:
        messages.error(request, "You can only add a maximum of 2 bank accounts.")
        return redirect(f"{request.build_absolute_uri('/admanager/settings/')}?tab=bank")
    form = BankAccountForm(request.POST)
    if form.is_valid():
        acct = form.save(commit=False)
        acct.ad_manager = ad_manager
        # Auto-default if first account
        if not ad_manager.bank_accounts.exists():
            acct.is_default = True
        acct.save()
        messages.success(request, f"Bank account ({acct.bank_name}) added successfully.")
    else:
        for field, errs in form.errors.items():
            for err in errs:
                messages.error(request, f"{field.replace('_', ' ').title()}: {err}")
    return redirect('/admanager/settings/?tab=bank')


@login_required(login_url='security:login')
@ad_manager_required
def bank_account_set_default(request, pk):
    if request.method != 'POST':
        return redirect('admanager:settings')
    ad_manager = request.user.ad_manager
    acct = get_object_or_404(BankAccount, pk=pk, ad_manager=ad_manager)
    acct.is_default = True
    acct.save()  # BankAccount.save() clears others automatically
    messages.success(request, f"{acct.bank_name} set as your default account.")
    return redirect('/admanager/settings/?tab=bank')


@login_required(login_url='security:login')
@ad_manager_required
def bank_account_delete(request, pk):
    if request.method != 'POST':
        return redirect('admanager:settings')
    ad_manager = request.user.ad_manager
    acct = get_object_or_404(BankAccount, pk=pk, ad_manager=ad_manager)
    # If deleting the default and there's another account, auto-promote the other
    if acct.is_default:
        other = ad_manager.bank_accounts.exclude(pk=pk).first()
        if other:
            other.is_default = True
            other.save()
    acct.delete()
    messages.success(request, "Bank account removed.")
    return redirect('/admanager/settings/?tab=bank')


@login_required(login_url='security:login')
@ad_manager_required
def billboard_list(request):
    ad_manager = request.user.ad_manager
    billboards = Billboard.objects.filter(ad_manager=ad_manager).order_by('-created_at')

    # ── Search & filter ──────────────────────────────────────────────
    search_query     = request.GET.get('search', '').strip()
    availability_f   = request.GET.get('availability', '')
    screen_type_f    = request.GET.get('screen_type', '')
    state_f          = request.GET.get('state', '')

    if search_query:
        billboards = billboards.filter(
            models.Q(name__icontains=search_query) |
            models.Q(location_name__icontains=search_query)
        )
    if availability_f:
        billboards = billboards.filter(availability=availability_f)
    if screen_type_f:
        billboards = billboards.filter(screen_type=screen_type_f)
    if state_f:
        billboards = billboards.filter(state=state_f)

    # Distinct states for the filter dropdown
    states = (
        Billboard.objects
        .filter(ad_manager=ad_manager)
        .values_list('state', flat=True)
        .distinct()
        .order_by('state')
    )

    return render(request, 'adManager/billboard_list.html', {
        'ad_manager': ad_manager,
        'billboards': billboards,
        'search_query': search_query,
        'selected_availability': availability_f,
        'selected_screen_type': screen_type_f,
        'selected_state': state_f,
        'states': states,
    })


@login_required(login_url='security:login')
@ad_manager_required
def billboard_create(request):
    ad_manager = request.user.ad_manager
    if request.method == 'POST':
        form = BillboardForm(request.POST, request.FILES)
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
        form = BillboardForm(request.POST, request.FILES, instance=billboard)
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
        campaign_slots__billboard__ad_manager=ad_manager
    ).exclude(
        status__in=[Campaign.Status.DRAFT, Campaign.Status.PENDING_ADMIN_REVIEW]
    ).distinct().select_related('advertiser', 'media').order_by('-updated_at')

    # ── Search & filter ──────────────────────────────────────────────
    search_query = request.GET.get('search', '').strip()
    status_f     = request.GET.get('status', '')

    if search_query:
        campaigns = campaigns.filter(
            models.Q(name__icontains=search_query) |
            models.Q(advertiser__business_name__icontains=search_query) |
            models.Q(media__title__icontains=search_query)
        )
    if status_f:
        campaigns = campaigns.filter(status=status_f)

    return render(request, 'adManager/campaign_requests.html', {
        'ad_manager': ad_manager,
        'campaigns': campaigns,
        'search_query': search_query,
        'selected_status': status_f,
    })


@login_required(login_url='security:login')
@ad_manager_required
def campaign_request_detail(request, pk):
    from django.http import Http404
    ad_manager = request.user.ad_manager
    campaign = get_object_or_404(
        Campaign,
        pk=pk,
        campaign_slots__billboard__ad_manager=ad_manager,
    )
    if campaign.status in [Campaign.Status.DRAFT, Campaign.Status.PENDING_ADMIN_REVIEW]:
        raise Http404("Campaign not found.")

    if request.method == 'POST':
        if campaign.status != Campaign.Status.PENDING_MANAGER_REVIEW:
            messages.error(request, "This campaign is not pending review.")
            return redirect('admanager:campaign_request_detail', pk=pk)

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


@login_required(login_url='security:login')
@ad_manager_required
def withdrawal_list_and_create(request):
    from decimal import Decimal
    ad_manager = request.user.ad_manager

    # Recalculate revenue first to display accurate balance
    ad_manager.revenue = ad_manager.calculate_revenue()
    ad_manager.save(update_fields=['revenue'])

    # Get default bank account for disbursement
    default_account = ad_manager.bank_accounts.filter(is_default=True).first()
    has_bank_account = ad_manager.bank_accounts.exists()

    if request.method == 'POST':
        # Block if no bank account is configured
        if not default_account:
            messages.error(request, "You must add a bank account before making a withdrawal request.")
            return redirect('admanager:withdrawal_list')

        amount_str = request.POST.get('amount', '').strip()
        notes = request.POST.get('notes', '').strip()

        # Build bank_details string from the default account
        bank_details = (
            f"{default_account.bank_name} | "
            f"{default_account.account_number} | "
            f"{default_account.account_name}"
        )

        try:
            amount = Decimal(amount_str)
            if amount <= 0:
                raise ValidationError("Withdrawal amount must be greater than zero.")
            if amount > ad_manager.available_balance:
                raise ValidationError(f"Insufficient balance. Your available balance is ₦{ad_manager.available_balance:,.2f}.")

            WithdrawalRequest.objects.create(
                ad_manager=ad_manager,
                amount=amount,
                bank_details=bank_details,
                notes=notes
            )
            messages.success(request, "Withdrawal request submitted successfully.")
            return redirect('admanager:withdrawal_list')
        except (ValueError, ValidationError) as e:
            messages.error(request, f"Error: {e}")
        except Exception:
            messages.error(request, "Invalid amount entered.")
        return redirect('admanager:withdrawal_list')

    withdrawals = ad_manager.withdrawal_requests.order_by('-created_at')

    context = {
        'ad_manager': ad_manager,
        'withdrawals': withdrawals,
        'revenue': ad_manager.revenue,
        'total_withdrawn': ad_manager.total_withdrawn,
        'pending_withdrawal': ad_manager.pending_withdrawal,
        'available_balance': ad_manager.available_balance,
        'default_account': default_account,
        'has_bank_account': has_bank_account,
    }
    return render(request, 'adManager/withdrawals.html', context)
