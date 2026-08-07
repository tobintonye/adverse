
from payments.services import ( create_paystack_subaccount)
from django.contrib.auth import get_user_model
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.db.models.functions import TruncMonth, TruncYear
from django.utils import timezone
from datetime import timedelta
import json
from django.db import transaction
from admanager.decorators import ad_manager_required
from .models import Admanager
from security.models import CustomUser
from advertiser.models import Campaign
from payments.models import AdManagerEarning
from .forms import AdManagerProfileForm
from django.core.exceptions import ValidationError, PermissionDenied
from advertiser.models import Campaign
from advertiser.services import approve_campaign_by_manager, reject_campaign
from django.db.models import Q
from scheduling.models import ScheduleGenerationLog
from django.core.paginator import Paginator
from scheduling.models import TimeSlot
import logging

logger = logging.getLogger(__name__)

try:
    from payments.models import AdManagerSubaccount
except ImportError:
    AdManagerSubaccount = None
 
def _get_campaign_for_manager(ad_manager, pk):
    """
    Return a campaign that includes this manager's billboard.
    Raises 404 if not found, 403 if this manager has no ownership.
    """
    campaign = get_object_or_404(
        Campaign.objects.select_related("advertiser", "media").prefetch_related(
            "campaign_slots__billboard"
        ),
        pk=pk,
    )
    has_ownership = campaign.campaign_slots.filter(
        billboard__ad_manager=ad_manager
    ).exists()
    if not has_ownership:
        raise PermissionDenied("You do not have permission to manage this campaign.")
    return campaign
 

User = get_user_model()
@login_required(login_url='security:login')
def adManagerProfile(request):
    if request.user.role != CustomUser.UserRole.AD_MANAGER:
        messages.error(request, "This account is not registered as an ad manager.")
        return redirect("security:login")

    # Create the Admanager profile for the logged-in user.
    if hasattr(request.user, 'ad_manager'):
        messages.info(request, "Your profile already exists.")
        return redirect("admanager:dashboard")
 
    if request.method == "POST":
        form = AdManagerProfileForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                profile = form.save(commit=False)
                profile.user = request.user
                profile.save()
            messages.success(request, "Profile created! Your account is pending verification.")
            return redirect("admanager:dashboard")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    if field == "__all__":
                        messages.error(request, error)
                    else:
                        label = form.fields[field].label or field.replace('_', ' ').capitalize()
                        messages.error(request, f"{label}: {error}")
    else:
        form = AdManagerProfileForm()
    return render(request, "adManager/profile.html", {"form": form})

@login_required(login_url='security:login')
@ad_manager_required
def adManagerProfile_edit(request):
    """
    Edit an existing Admanager profile.
    Blocked for suspended accounts.
    """
    ad_manager = get_object_or_404(Admanager, user=request.user)
 
    if ad_manager.verification_status == Admanager.VerificationStatus.SUSPENDED:
        messages.error(request, "Suspended accounts cannot update their profile.")
        return redirect("admanager:dashboard")
 
    if request.method == "POST":
        form = AdManagerProfileForm(request.POST, instance=ad_manager)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully.", extra_tags="profile")
            return redirect("admanager:dashboard")
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    label = form.fields[field].label or field.replace('_', ' ').capitalize()
                    messages.error(request, f"{label}: {error}")
    else:
        form = AdManagerProfileForm(instance=ad_manager)
    return render(request, "adManager/edit_profile.html", {"form": form, "ad_manager": ad_manager})

@login_required(login_url='security:login')
@ad_manager_required
def adManagerDashboard(request):
    try:
        ad_manager = request.user.ad_manager
    except Admanager.DoesNotExist:
        messages.error(request, "Ad manager profile not found.")
        return redirect("security:login")

    if request.method == "POST" and "request_verification" in request.POST:
        try:
            ad_manager.request_verification()
            messages.success(request, "Verification request submitted. Our admin team will review your account shortly.")
        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, "message") else str(e))
        return redirect("admanager:dashboard")

    # Inventory & campaign stats (live counts, no caching drift)
    total_billboards = ad_manager.billboards.count()
    total_campaigns_served = ad_manager.received_campaigns.filter(
        status__in=[Campaign.Status.APPROVED, Campaign.Status.ACTIVE, Campaign.Status.COMPLETED]
    ).count()
    pending_requests_count = ad_manager.pending_review_campaigns.count()

    today = timezone.now().date()

    # Financials — Paystack pays the ad manager directly via subaccount
    # split, so this is a record of what's been earned, not a balance
    # to withdraw. total_withdrawn / pending_withdrawal / available_balance
    # (all PayoutRecord-based) removed since there's no withdrawal flow anymore.
    revenue = AdManagerEarning.objects.filter(
        ad_manager=ad_manager
    ).aggregate(total=Sum("amount"))["total"] or 0

    this_month_earnings = AdManagerEarning.objects.filter(
        ad_manager=ad_manager,
        earned_at__year=today.year,
        earned_at__month=today.month,
    ).aggregate(total=Sum("amount"))["total"] or 0

    # Delivery rate — confirmed plays vs scheduled plays that have already
    # happened (excludes future/upcoming slots, since those haven't had a
    # chance to play yet and shouldn't drag the rate down unfairly)
    past_slots = TimeSlot.objects.filter(
        billboard__ad_manager=ad_manager,
        date__lte=today,
    )
    total_past_slots = past_slots.count()
    confirmed_past_slots = past_slots.filter(
        playback_logs__completed=True
    ).distinct().count()
    delivery_rate = (
        round((confirmed_past_slots / total_past_slots) * 100, 1)
        if total_past_slots else None
    )

    # Revenue analytics charts (DB-side aggregation, not a Python loop)
    twelve_months_ago = today.replace(day=1) - timedelta(days=365)
    monthly_qs = (
        AdManagerEarning.objects.filter(
            ad_manager=ad_manager, earned_at__date__gte=twelve_months_ago
        )
        .annotate(month=TruncMonth("earned_at"))
        .values("month")
        .annotate(total=Sum("amount"))
        .order_by("month")
    )
    monthly_labels = [row["month"].strftime("%b %Y") for row in monthly_qs]
    monthly_values = [float(row["total"]) for row in monthly_qs]

    five_years_ago = today.replace(month=1, day=1) - timedelta(days=365 * 5)
    annual_qs = (
        AdManagerEarning.objects.filter(
            ad_manager=ad_manager, earned_at__date__gte=five_years_ago
        )
        .annotate(year=TruncYear("earned_at"))
        .values("year")
        .annotate(total=Sum("amount"))
        .order_by("year")
    )
    annual_labels = [row["year"].strftime("%Y") for row in annual_qs]
    annual_values = [float(row["total"]) for row in annual_qs]

    subaccount = getattr(ad_manager, "paystack_subaccount", None)
    subaccount_inactive = subaccount and not subaccount.is_active
    subaccount_unverified = subaccount and subaccount.is_active and not subaccount.is_verified

    chart_data = {
        "monthlyLabels": monthly_labels,
        "monthlyValues": monthly_values,
        "annualLabels": annual_labels,
        "annualValues": annual_values,
    }

    context = {
        "ad_manager": ad_manager,
        # Profile/status
        "business_name": ad_manager.business_name,
        "business_type": ad_manager.business_type,
        "verification_status": ad_manager.verification_status,
        "is_verified": ad_manager.is_verified,
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
        # Inventory & output stats
        "total_billboards": total_billboards,
        "total_campaigns_served": total_campaigns_served,
        "total_impressions": ad_manager.total_impressions,  # we have to get this
        "pending_requests_count": pending_requests_count,
        # Financials
        "revenue": revenue,
        "this_month_earnings": this_month_earnings,
        "delivery_rate": delivery_rate,
        "commission_rate": ad_manager.commission_rate,
        "has_bank_account": ad_manager.has_bank_account,
        # Chart data
        "monthly_labels_json": json.dumps(monthly_labels),
        "monthly_values_json": json.dumps(monthly_values),
        "annual_labels_json": json.dumps(annual_labels),
        "annual_values_json": json.dumps(annual_values),
        "chart_data": chart_data,
        "subaccount": subaccount,
        "subaccount_inactive": subaccount_inactive,
        "subaccount_unverified": subaccount_unverified,
    }

    return render(request, "adManager/dashboard.html", context)

@login_required(login_url='security:login')
@ad_manager_required
def campaign_requests(request):
    """
    All campaigns booking this manager's billboards — not just pending ones.
    Filterable by status and a free-text search across name / advertiser / media title.
    """
    ad_manager = request.user.ad_manager
 
    campaigns = (
        Campaign.objects.filter(campaign_slots__billboard__ad_manager=ad_manager)
        .exclude(status=Campaign.Status.DRAFT) 
        .select_related("advertiser", "media")
        .distinct()
        .order_by("-created_at")
    )
 
    search_query = request.GET.get("search", "").strip()
    if search_query:
        campaigns = campaigns.filter(
            Q(name__icontains=search_query)
            | Q(advertiser__business_name__icontains=search_query)
            | Q(media__title__icontains=search_query)
        )
 
    selected_status = request.GET.get("status", "").strip()
    if selected_status:
        campaigns = campaigns.filter(status=selected_status)
    
    paginator = Paginator(campaigns, 15)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        "campaigns": page_obj,
        "page_obj": page_obj,
        "search_query": search_query,
        "selected_status": selected_status,
    }

    # HTMX pagination/filter request — return just the table partial
    if request.headers.get("HX-Request"):
        return render(request, "adManager/partials/campaign_requests_table.html", context)
 
    return render(request, "adManager/campaign_requests.html", context)
 

@login_required(login_url='security:login')
@ad_manager_required
def campaign_request_detail(request, pk):
    """
    Full detail + the approve/reject decision form.
    GET  -> show details (and the decision form if still pending review)
    POST -> action=approve | action=reject, reason=<text if rejecting>
    """
    ad_manager = request.user.ad_manager
 
    try:
        campaign = _get_campaign_for_manager(ad_manager, pk)
    except PermissionDenied:
        messages.error(request, "You do not have permission to view this campaign.")
        return redirect("admanager:campaign_requests")
 
    if request.method == "POST":
        if campaign.status != Campaign.Status.PENDING_MANAGER_REVIEW:
            messages.error(request, "This campaign is no longer pending your review.")
            return redirect("admanager:campaign_requests")
 
        action = request.POST.get("action")
        reason = request.POST.get("reason", "").strip()
 
        if action == "approve":
            try:
                result = approve_campaign_by_manager(
                    campaign=campaign,
                    manager_user=request.user,
                )
                warning = (
                    f" {result['slots_skipped']} slot(s) were skipped due to billboard capacity."
                    if result.get("slots_skipped")
                    else ""
                )
                messages.success(
                    request,
                    f"Campaign '{campaign.name}' approved and deployed live.{warning}",
                )
            except ValidationError as e:
                messages.error(
                    request,
                    e.message if hasattr(e, "message") else "; ".join(e.messages),
                )
            return redirect("admanager:campaign_requests")
 
        elif action == "reject":
            if not reason:
                messages.error(request, "Please provide a rejection reason.")
            else:
                try:
                    reject_campaign(campaign=campaign, reviewer=request.user, reason=reason)
                    messages.success(request, f"Campaign '{campaign.name}' has been rejected.")
                    return redirect("admanager:campaign_requests")
                except ValidationError as e:
                    messages.error(
                        request,
                        e.message if hasattr(e, "message") else "; ".join(e.messages),
                    )
        else:
            messages.error(request, "Invalid action.")
    # testing
    schedule_logs = ScheduleGenerationLog.objects.filter(campaign=campaign).order_by("-generated_at")

    context = {
        "campaign": campaign,
        "slots": campaign.campaign_slots.select_related("billboard").all(),
        "schedule_logs": schedule_logs,
    }
    return render(request, "adManager/campaign_request_detail.html", context)

@login_required(login_url='security:login')
@ad_manager_required
def campaign_schedule_log(request, pk):
    """
    Shows every schedule generation run for a campaign useful when
    slots_skipped > 0 and the manager wants to know exactly which
    billboard/date ran out of capacity, not just the total count.
    """

    ad_manager = request.user.ad_manager
    campaign = get_object_or_404(Campaign.objects.select_related("advertiser"), pk=pk)
    has_ownership = campaign.campaign_slots.filter(billboard__ad_manager=ad_manager).exists()
    if not has_ownership:
        raise PermissionDenied("You do not have permission to view this campaign's schedule log.")
 
    logs = ScheduleGenerationLog.objects.filter(campaign=campaign).order_by("-generated_at")
 
    context = {
        "campaign": campaign,
        "logs": logs,
    }
    if request.headers.get("HX-Request"):
       return render(request, "adManager/partials/campaign_schedule_log_list.html", context)
    return render(request, "adManager/campaign_schedule_log.html", context)


@login_required(login_url='security:login')
@ad_manager_required
def campaign_playback_log(request, pk):
    """
    Slot-by-slot reconciliation: every TimeSlot scheduled for this campaign
    on this ad manager's billboards, matched against whether a PlaybackLog
    confirms it actually played.
    """

    ad_manager = request.user.ad_manager
    campaign = _get_campaign_for_manager(ad_manager, pk)

    time_slots = (TimeSlot.objects.filter(campaign=campaign, billboard__ad_manager=ad_manager).select_related("billboard").prefetch_related("playback_logs").order_by("date", "play_order"))

    today = timezone.now().date()
    rows = []
    for ts in time_slots:
        log = ts.playback_logs.filter(completed=True).order_by("started_at").first()
        if log:
            state = "confirmed"
        elif ts.date > today:
            state = "upcoming"
        else:
            state = "missed"
        rows.append({"time_slot": ts, "log": log, "state": state})

    total = len(rows)
    confirmed_count = sum(1 for r in rows if r["state"] == "confirmed")
    missed_count = sum(1 for r in rows if r["state"] == "missed")
    upcoming_count = sum(1 for r in rows if r["state"] == "upcoming")

    context = {
        "campaign": campaign,
        "rows": rows,
        "total": total,
        "confirmed_count": confirmed_count,
        "missed_count": missed_count,
        "upcoming_count": upcoming_count,
        "confirmed_pct": round((confirmed_count / total) * 100, 1) if total else 0,
    }

    if request.headers.get("HX-Request"):
        return render(request, "adManager/partials/campaign_playback_log_table.html", context)
    return render(request, "adManager/campaign_playback_log.html", context)

@login_required(login_url='security:login')
@ad_manager_required
def adManager_setting(request):
    ad_manager = request.user.ad_manager
    active_tab = request.GET.get('tab', 'business')

    if request.method == 'POST' and 'save_business' in request.POST:
        form = AdManagerProfileForm(request.POST, instance=ad_manager)
        if form.is_valid():
            form.save()
            messages.success(request, 'Business information updated successfully.')
            return redirect(f"{request.path}?tab=business")
        else:
            active_tab = 'business'
            for field, errors in form.errors.items():
                for error in errors:
                    if field == "__all__":
                        messages.error(request, error)
                    else:
                        label = form.fields[field].label or field.replace('_', ' ').capitalize()
                        messages.error(request, f"{label}: {error}")
    else:
        form = AdManagerProfileForm(instance=ad_manager)

    # Bank accounts — model doesn't exist yet, stub as empty so the
    # "Bank Details" tab renders without crashing. Swap this out for
    # ad_manager.bank_accounts.all() once BankAccount is built.
    bank_accounts = []
    context = {
        "admanager": ad_manager,
        "form": form,
        "bank_accounts": bank_accounts,
        "active_tab": active_tab,
    }

    if request.headers.get("HX-Request"):
        return render(request, "adManager/partials/settings_tabs.html", context)

    return render(request, "adManager/settings.html", context)

@login_required(login_url="security:login")
@ad_manager_required
def payment_setup(request):
    """
    GET  /admanager/payment/setup/
         Show the subaccount setup form (or existing details if already set up).
 
    POST /admanager/payment/setup/
         Create a new Paystack subaccount for this ad manager.
         Calls create_paystack_subaccount() from payments.services — this
         hits Paystack's name enquiry API then creates the subaccount.
         Only the last 4 digits of the account number are stored locally.
    """
    from payments.models import AdManagerSubaccount
    ad_manager = request.user.ad_manager
    # Resolve existing subaccount if present
    subaccount = getattr(ad_manager, "paystack_subaccount", None)

    # Allow recreation if subaccount exists but is inactive
    subaccount_inactive = subaccount and not subaccount.is_active
    
    if request.method == "POST" and (not subaccount or subaccount_inactive):
        bank_code = request.POST.get("bank_code", "").strip()
        account_number = request.POST.get("account_number", "").strip()
        business_name = request.POST.get("business_name", "").strip()

        # Basic frontend-mirrored validation before hitting Paystack
        errors = []
        if not bank_code:
            errors.append("Please select a bank.")
        if not account_number.isdigit() or len(account_number) != 10:
            errors.append("Account number must be exactly 10 digits.")
        if not business_name:
            errors.append("Business name is required.")
        if errors:
            for e in errors:
                messages.error(request, e)
        else:
            try:
                # Detach the old inactive subaccount instead of deleting
                if subaccount_inactive:
                    old_subaccount = subaccount
                    old_subaccount.ad_manager = None
                    old_subaccount.subaccount_code = (
                        f"{old_subaccount.subaccount_code}__superseded_"
                        f"{timezone.now().strftime('%Y%m%d%H%M%S')}"
                        )
                    old_subaccount.save(
                        update_fields=["ad_manager", "subaccount_code", "updated_at"]
                        )

                subaccount = create_paystack_subaccount(ad_manager=ad_manager, bank_code=bank_code, account_number=account_number, business_name=business_name)
                messages.success(request, "Bank account connected successfully. Your subaccount will be verified before payments are processed.")
                return redirect("admanager:payment_setup")
            except ValidationError as e:
                messages.error(request, str(e))

    return render(request, "adManager/payment_setup.html", {
        "ad_manager": ad_manager,
        "subaccount": subaccount,
        "subaccount_inactive": subaccount_inactive,
    })
    
@login_required(login_url="security:login")
@ad_manager_required
def payment_update_bank(request):
    """
    POST /admanager/payment/update-bank/
 
    Updates the bank details on an existing Paystack subaccount.
    Calls update_paystack_subaccount_bank_details() from payments.services —
    this hits Paystack's name enquiry API, updates the subaccount on Paystack,
    and saves only the last 4 digits locally.
 
    Always redirects — no GET for this endpoint.
    """
    from payments.services import update_paystack_subaccount_bank_details

    if request.method != "POST":
        return redirect("admanager:payment_setup")
    
    ad_manager = request.user.ad_manager
    subaccount = getattr(ad_manager, "paystack_subaccount", None)

    if not subaccount:
        messages.error(request, "No subaccount found. Please set up payment details first.")
        return redirect("admanager:payment_setup")
    
    bank_code = request.POST.get("bank_code", "").strip()
    account_number = request.POST.get("account_number", "").strip()
    business_name = request.POST.get("business_name", "").strip() or None

    errors = []
    if not bank_code:
        errors.append("Please select a bank.")
    if not account_number.isdigit() or len(account_number) != 10:
        errors.append("Account number must be exactly 10 digits.")
    if errors:
        for e in errors:
            messages.error(request, e)
        return redirect("admanager:payment_setup")
    
    try:
        update_paystack_subaccount_bank_details(subaccount=subaccount, bank_code=bank_code, account_number=account_number, business_name=business_name, updated_by=request.user)
        messages.success(request, "Bank details updated. Your subaccount is pending re-verification — " "payments are paused until the new account is confirmed.")
    except ValidationError as e:
        messages.error(request, str(e))
    
    return redirect("admanager:payment_setup")


@login_required(login_url="security:login")
@ad_manager_required
def payment_verify_subaccount(request):
    """
    POST /admanager/payment/verify/
    Checks the subaccount status on Paystack and marks it verified locally
    if Paystack confirms it. Called manually by the ad manager or by staff.
    """
    if request.method != "POST":
        return redirect("admanager:payment_setup")

    ad_manager = request.user.ad_manager
    subaccount = getattr(ad_manager, "paystack_subaccount", None)

    if not subaccount:
        messages.error(request, "No subaccount found. Please set up payment details first.")
        return redirect("admanager:payment_setup")
    if subaccount.is_verified and subaccount.is_active:
        messages.info(request, "Your subaccount is already verified.")
        return redirect("admanager:payment_setup")

    try:
        from payments.services import _paystack_get
        data = _paystack_get(
            f"https://api.paystack.co/subaccount/{subaccount.subaccount_code}"
        )
        paystack_subaccount = data.get("data", {})
        is_verified = paystack_subaccount.get("is_verified", False)

        if is_verified:
            subaccount.mark_verified(changed_by=request.user)
            if not subaccount.is_active:
                subaccount.reactivate(changed_by=request.user)
            messages.success(request, "Subaccount verified successfully. You can now receive payments.")
        else:
            messages.warning(request, "Paystack has not verified this subaccount yet. Please try again shortly.")

    except Exception:
        logger.exception("Paystack subaccount verification failed for ad_manager %s", ad_manager.pk,)
        messages.error(request, "Could not check verification status right now. Please try again shortly.")

    return redirect("admanager:payment_setup")

@login_required(login_url='security:login')
@ad_manager_required
def earnings_history(request):
    """
    Read-only history of everything this ad manager has earned. No
    withdrawal action here — Paystack already paid each amount directly
    to their bank account the moment the advertiser's payment cleared.
    """
    ad_manager = request.user.ad_manager
    revenue = AdManagerEarning.objects.filter(
        ad_manager=ad_manager
    ).aggregate(total=Sum("amount"))["total"] or 0

    earnings = AdManagerEarning.objects.filter(
        ad_manager=ad_manager
    ).select_related("payment__campaign").order_by("-earned_at")

    context = {
        "total_earned": revenue,
        "earnings": earnings,
    }
    return render(request, "adManager/earnings_history.html", context)