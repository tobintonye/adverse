from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncMonth, TruncYear
from django.utils import timezone
from datetime import timedelta
import json
from .forms import AdvertiserProfileForm, MediaUploadForm, CampaignForm
from advertiser.decorators import advertiser_required
from .models import Advertiser, Campaign, CampaignSlot, Media
from device.models import Billboard
from django.db import transaction
from payments.services import initialize_campaign_payment


def _get_advertiser(request):
    """Single place to resolve the advertiser — raises if profile missing."""
    return request.user.advertiser_profile

def _campaign_error_messages(request, form):
    for field, errors in form.errors.items():
        for error in errors:
            if field == "__all__":
                messages.error(request, error)
            else:
                label = form.fields[field].label or field.replace("_", " ").capitalize()
                messages.error(request, f"{label}: {error}")


@login_required(login_url='security:login')
def advertiser_create_profile(request):
    if hasattr(request.user, 'advertiser_profile'):
        messages.info(request, "Your profile already exists.")
        return redirect("advertiser:dashboard")
 
    if request.method == "POST":
        form = AdvertiserProfileForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                profile = form.save(commit=False)
                profile.user = request.user
                profile.save()
            messages.success(request, "Profile created! Your account is pending verification.")
            return redirect("advertiser:dashboard")
        else:
            _campaign_error_messages(request, form)
    else:
        form = AdvertiserProfileForm()
 
    return render(request, "advertiser/create_profile.html", {"form": form})


@login_required(login_url="security:login")
@advertiser_required
def advertiser_edit_profile(request):
    advertiser = get_object_or_404(Advertiser, user=request.user)

    if request.method == "POST":
        form = AdvertiserProfileForm(request.POST, instance=advertiser)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("advertiser:settings")
        else:
            _campaign_error_messages(request, form)
    else: 
        form = AdvertiserProfileForm(advertiser=advertiser)
    return render(request, "advertiser/edit_profile.html", {"form": form, "advertiser": advertiser})

# verification
@login_required(login_url="security:login")
@advertiser_required
def advertiser_request_verification(request):
    advertiser = _get_advertiser(request)
    if request.method == "POST":
        try:
            advertiser.request_verification()
            messages.success(request, "Verification request submitted. Our admin team will review your account shortly")
        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, "message") else str(e))
    return redirect("advertiser:dashboard")

@login_required(login_url="security:login")
@advertiser_required
def advertiserDashboard(request):
    advertiser = _get_advertiser(request)
    campaigns = Campaign.objects.filter(advertiser=advertiser)
    billed_statuses = [
        Campaign.Status.APPROVED,
        Campaign.Status.ACTIVE,
        Campaign.Status.COMPLETED,
    ]
 
    total_lifetime_budget = (
        campaigns.filter(status__in=billed_statuses)
        .aggregate(total=Sum("actual_price"))["total"] or 0
    )
    total_active_budget = (
        campaigns.filter(status=Campaign.Status.ACTIVE)
        .aggregate(total=Sum("actual_price"))["total"] or 0
    )
    active_campaigns = campaigns.filter(status=Campaign.Status.ACTIVE).count()
    pending_campaigns = campaigns.filter(
        status__in=[
            Campaign.Status.PENDING_ADMIN_REVIEW,
            Campaign.Status.PENDING_MANAGER_REVIEW,
        ]
    ).count()
    draft_campaigns_count = campaigns.filter(status=Campaign.Status.DRAFT).count()
    rejected_campaigns_count = campaigns.filter(status=Campaign.Status.REJECTED).count()
 
    # Sum slots_per_day across all active campaign slots
    daily_slots_booked = sum(
        slot.slots_per_day
        for c in campaigns.filter(status=Campaign.Status.ACTIVE).prefetch_related("campaign_slots")
        for slot in c.campaign_slots.all()
    )
 
    media_qs = Media.objects.filter(advertiser=advertiser)
    media_count = media_qs.count()
    total_media_size_bytes = media_qs.aggregate(total=Sum("file_size_bytes"))["total"] or 0
    total_media_size_mb = round(total_media_size_bytes / (1024 * 1024), 2)
 
    recent_campaigns = campaigns.select_related("media").order_by("-created_at")[:5]
 
    today = timezone.now().date()
    twelve_months_ago = today.replace(day=1) - timedelta(days=365)
    monthly_qs = (
        campaigns.filter(status__in=billed_statuses, created_at__date__gte=twelve_months_ago)
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(total=Sum("actual_price"))
        .order_by("month")
    )
    monthly_labels = [row["month"].strftime("%b %Y") for row in monthly_qs]
    monthly_values = [float(row["total"]) for row in monthly_qs]
 
    five_years_ago = today.replace(month=1, day=1) - timedelta(days=365 * 5)
    annual_qs = (
        campaigns.filter(status__in=billed_statuses, created_at__date__gte=five_years_ago)
        .annotate(year=TruncYear("created_at"))
        .values("year")
        .annotate(total=Sum("actual_price"))
        .order_by("year")
    )
    annual_labels = [row["year"].strftime("%Y") for row in annual_qs]
    annual_values = [float(row["total"]) for row in annual_qs]
 
    context = {
        "advertiser": advertiser,
        "total_lifetime_budget": total_lifetime_budget,
        "total_active_budget": total_active_budget,
        "active_campaigns": active_campaigns,
        "pending_campaigns": pending_campaigns,
        "draft_campaigns_count": draft_campaigns_count,
        "rejected_campaigns_count": rejected_campaigns_count,
        "daily_slots_booked": daily_slots_booked,
        "media_count": media_count,
        "total_media_size_mb": total_media_size_mb,
        "recent_campaigns": recent_campaigns,
        "monthly_labels_json": json.dumps(monthly_labels),
        "monthly_values_json": json.dumps(monthly_values),
        "annual_labels_json": json.dumps(annual_labels),
        "annual_values_json": json.dumps(annual_values),
    }
    return render(request, "advertiser/dashboard.html", context)


# media libbrary
@login_required(login_url="security:login")
@advertiser_required
def media_library(request):
    advertiser = _get_advertiser(request)
    today = timezone.now().date()
     # Auto-expire campaigns whose end_date has passed — self-heals without Celery
    expired = Campaign.objects.filter(advertiser=advertiser, status=Campaign.Status.ACTIVE, end_date__lt=today,)
    if expired.exists():
        expired.update(status=Campaign.Status.COMPLETED)
    media_items = advertiser.media_files.prefetch_related("campaigns").order_by("-created_at")

    # Build a set of media IDs that have active campaigns right now
    active_media_ids = set(
        Campaign.objects.filter(advertiser=advertiser,status=Campaign.Status.ACTIVE,end_date__gte=today,).values_list("media_id", flat=True))

    completed_media_ids = set(
        Campaign.objects.filter(
            advertiser=advertiser,
            status=Campaign.Status.COMPLETED,
        ).values_list("media_id", flat=True)
    )

    media_files = Media.objects.filter(advertiser=advertiser).order_by("-created_at")
    return render(request, "advertiser/media_library.html", {
        "media_files": media_files,
        "media_items": media_items,
        "active_media_ids": active_media_ids,
        "completed_media_ids": completed_media_ids,
        "today": today,
        })
 
@login_required(login_url="security:login")
@advertiser_required
def upload_media(request):
    advertiser = _get_advertiser(request)

    if request.method == "POST":
        form = MediaUploadForm(request.POST, request.FILES)
        if form.is_valid():
            media = form.save(commit=False)
            media.advertiser = advertiser
            try:
                media.save()
                messages.success(request, f"'{media.title}' uploaded successfully. It's pending admin review.")
            except ValidationError as e:
                error_dict = ( e.message_dict if hasattr(e, "message_dict") else {"__all__": e.messages})
                for field, errors in error_dict.items():
                    for error in errors:
                        messages.error(request, error)
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    if field == "__all__":
                        messages.error(request, error)
                    else:
                        label = form.fields[field].label or field.replace("_", " ").capitalize()
                        messages.error(request, f"{label}: {error}")
    else:
        form = MediaUploadForm()
    return render(request, "advertiser/upload_media.html", {"form": form})

@login_required(login_url="security:login")
@advertiser_required
def media_delete(request, pk):
    # POST-only. Only PENDING/REJECTED media can be deleted.
    advertiser = _get_advertiser(request)
    media = get_object_or_404(Media, pk=pk, advertiser=advertiser)

    if request.method != "POST":
        return redirect("advertiser:media_library")
    
    if media.status not in [Media.Status.PENDING, Media.Status.REJECTED]:
        messages.error(request,  f"'{media.title}' has been approved and may be referenced by a campaign — it can't be deleted.")
        return redirect("advertiser:media_library")

    title = media.title
    media.delete()
    messages.success(request, f"'{title}' deleted.")
    return redirect("advertiser:media_library")

# browse billboards
@login_required(login_url="security:login")
@advertiser_required
def browse_billboards(request):
    billboards = (Billboard.objects.filter(availability=Billboard.Availability.AVAILABLE).select_related("ad_manager").order_by("name"))
    screen_type_choices = Billboard.ScreenType.choices
    return render(request, "advertiser/browse_billboards.html", {
        "billboards": billboards,
        "screen_type_choices": screen_type_choices,
    })

# campaigns 
@login_required(login_url="security:login")
@advertiser_required
def campaign_list(request):
    advertiser = _get_advertiser(request)
    campaigns = Campaign.objects.filter(advertiser=advertiser).select_related("media").order_by("-created_at")
    search_query = request.GET.get("search", "").strip()
    if search_query:
        campaigns = campaigns.filter(Q(name__icontains=search_query) | Q(media__title__icontains=search_query))

    selected_status = request.GET.get("status", "").strip()
    if selected_status:
        campaigns = campaigns.filter(status=selected_status)
    
    return render(request, "advertiser/campaign_list.html", {
        "campaigns": campaigns,
        "search_query": search_query,
        "selected_status": selected_status,
    })

def _build_billboards_json(available_billboards):
    """
    Serialise billboard queryset to a JS-safe dict keyed by pk string.
    Used by the campaign create/edit template's live price calculator.
    """
    result = {}
    for bb in available_billboards:
        media_url = bb.media_file.url if bb.media_file else None
        media_is_video = False
        if media_url:
            ext = media_url.rsplit(".", 1)[-1].lower()
            media_is_video = ext in ("mp4", "mov", "webm", "m4v", "3gp")
 
        result[str(bb.pk)] = {
            "name": bb.name,
            "location_name": bb.location_name,
            "state": bb.state,
            "country": bb.country,
            "screen_type": bb.get_screen_type_display(),
            "hours_start": str(bb.operating_hours_start)[:5],
            "hours_end": str(bb.operating_hours_end)[:5],
            "price": float(bb.price_per_slot),
            "charge_unit": bb.charge_unit,
            "media_url": media_url,
            "media_is_video": media_is_video,
        }
    return json.dumps(result)

@login_required(login_url="security:login")
@advertiser_required
def campaign_create(request):
    advertiser = _get_advertiser(request)
    available_billboards = Billboard.objects.filter(availability=Billboard.Availability.AVAILABLE).order_by("name")
    # ?billboard=<pk> from the "Book" button on browse_billboards
    preselected_billboard = request.GET.get("billboard", "")

    if request.method == "POST":
        form = CampaignForm(advertiser, request.POST)
        if form.is_valid():
            billboard_id = request.POST.get("billboard", "").strip()
            slots_per_day = int(request.POST.get("slots_per_day", 1) or 1)

            if not billboard_id:
                messages.error(request, "Please select a billboard.")
            else:
                billboard = get_object_or_404(Billboard, pk=billboard_id, availability=Billboard.Availability.AVAILABLE)
                try:
                    with transaction.atomic():
                        campaign = form.save(commit=False)
                        campaign.advertiser = advertiser
                        campaign.save()
                        CampaignSlot.objects.create(
                            campaign=campaign,
                            billboard=billboard,
                            slots_per_day=slots_per_day,
                        )
                        campaign.sync_estimated_price()
                    messages.success(request, f"'{campaign.name}' saved as draft.")
                    return redirect("advertiser:campaign_detail", pk=campaign.pk)
                except ValidationError as e:
                    messages.error(request, e.message if hasattr(e,"message") else str(e))
        else:
            _campaign_error_messages(request, form)
    else:
        form = CampaignForm(advertiser)
    
    context = {
        "form": form,
        "billboards_json": _build_billboards_json(available_billboards),
        "preselected_billboard": preselected_billboard,
    }
    # Inject the billboard queryset into the form field so the template can
    # iterate form.fields.billboard.queryset for the <select> options
    form.fields["billboard"] = _BillboardChoiceField(available_billboards)
    form.initial["billboard"] = preselected_billboard
    return render(request, "advertiser/campaign_create.html", context)

class _BillboardChoiceField:
    def __init__(self, queryset):
        self.queryset = queryset
    """
        Thin shim so the template can do form.fields.billboard.queryset
        without making CampaignForm a full ModelForm for Billboard.
        Not a real Django field — just exposes .queryset for template iteration.
    """

@login_required(login_url="security:login")
@advertiser_required        
def campaign_edit(request, pk):
    advertiser = _get_advertiser(request) 
    campaign = get_object_or_404(Campaign, pk=pk, advertiser=advertiser)

    if campaign.status not in [Campaign.Status.DRAFT, Campaign.Status.REJECTED]:
        messages.error(request, "This campaign can't be edited in its current status.")

        return redirect("advertiser:campaign_detail", pk=campaign.pk)
    
    available_billboards = Billboard.objects.filter(availability=Billboard.Availability.AVAILABLE).order_by("name")

    # Existing slot — one billboard per campaign in current UI
    existing_slot = campaign.campaign_slots.select_related("billboard").first()

    if request.method == "POST": 
        form = CampaignForm(advertiser, request.POST, instance=campaign)
        if form.is_valid():
            billboard_id = request.POST.get("billboard", "").strip()
            slots_per_day = int(request.POST.get("slots_per_day", 1) or 1)

            if not billboard_id:
                messages.error(request, "Please select a billboard.")
            else:
                billboard = get_object_or_404(Billboard, pk=billboard_id, availability=Billboard.Availability.AVAILABLE)
                try:
                    with transaction.atomic():
                        updated = form.save()
                        # Replace existing slot
                        updated.campaign_slots.all().delete()
                        CampaignSlot.objects.create(campaign=updated, billboard=billboard, slots_per_day=slots_per_day)
                        updated.sync_estimated_price()
                        messages.success(request, f"'{updated.name}' updated.")
                        return redirect("advertiser:campaign_detail", pk=updated.pk)
                except ValidationError as e:
                    messages.error(request, e.messages if hasattr(e, "message") else str(e))
        else:
            _campaign_error_messages(request, form)
    else:
        form = CampaignForm(advertiser, instance=campaign)

    # Pre-populate billboard select and slots_per_day from existing slot
    initial_billboard_pk = str(existing_slot.billboard.pk) if existing_slot else ""
    initial_slots_per_day = existing_slot.slots_per_day if existing_slot else 1
    form.fields["billboard"] = _BillboardChoiceField(available_billboards)
    form.initial["billboard"] = initial_billboard_pk
 
    context = {
        "form": form,
        "campaign": campaign,
        "billboards_json": _build_billboards_json(available_billboards),
        "preselected_billboard": initial_billboard_pk,
        "initial_slots_per_day": initial_slots_per_day,
    }
    return render(request, "advertiser/campaign_create.html", context)

@login_required(login_url="security:login")
@advertiser_required
def campaign_detail(request, pk):
    advertiser = _get_advertiser(request)
    campaign = get_object_or_404(
        Campaign.objects.select_related("media", "advertiser").prefetch_related(
            "campaign_slots__billboard"
        ),
        pk=pk,
        advertiser=advertiser,
    )

    # Auto-verify pending payment when advertiser views the campaign page
    try:
        payment = campaign.payment
        if payment and payment.status == "pending":
            from payments.services import handle_charge_success
            try:
                handle_charge_success({
                    "event": "charge.success",
                    "data": {"reference": payment.reference}
                })
                payment.refresh_from_db()
                campaign.refresh_from_db()
                if payment.status == "completed":
                    messages.success(
                        request,
                        "Payment confirmed! Your campaign is now active."
                    )
            except Exception:
                pass  # still pending, stay quiet
    except Exception:
        payment = None

    slots = campaign.campaign_slots.select_related("billboard").all()

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "submit":
            try:
                campaign.submit_for_approval()
                messages.success(request, "Campaign submitted for review.")
            except ValidationError as e:
                messages.error(request, e.message if hasattr(e, "message") else str(e))
        elif action == "cancel":
            try:
                campaign.cancel()
                messages.success(request, f"'{campaign.name}' has been cancelled.")
                return redirect("advertiser:campaign_list")
            except ValidationError as e:
                messages.error(request, e.message if hasattr(e, "message") else str(e))
        return redirect("advertiser:campaign_detail", pk=campaign.pk)

    return render(request, "advertiser/campaign_detail.html", {
        "campaign": campaign,
        "slots": slots,
        "payment": payment,
    })

@login_required(login_url="security:login")
@advertiser_required
def advertiser_settings(request):
    advertiser = _get_advertiser(request)

    if request.method == "POST":
        form = AdvertiserProfileForm(request.POST, instance=advertiser)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully.")
            return redirect("advertiser:settings")
        else:
            _campaign_error_messages(request, form)
    else:
        form = AdvertiserProfileForm(instance=advertiser)

    return render(request, "advertiser/settings.html", {"form": form, "advertiser": advertiser})

@login_required(login_url="security:login")
@advertiser_required
def campaign_pay(request, pk):
    """
    POST /advertiser/campaigns/<pk>/pay/
 
    Initiates a Paystack payment for an APPROVED campaign.
    Creates a CampaignPayment record (PENDING) then redirects the
    advertiser to Paystack's hosted checkout page.
 
    On return from Paystack, the advertiser lands back on campaign_detail.
    The actual mark_completed() happens via the Paystack webhook — NOT here.
 
    Guards:
    - Campaign must belong to this advertiser
    - Campaign must be APPROVED
    - No active PENDING or COMPLETED payment already exists
    """
    if request.method != "POST":
        return redirect("advertiser:campaign_detail", pk=pk)
    
    advertiser = _get_advertiser(request)
    campaign = get_object_or_404(Campaign.objects.select_related("advertiser", "payment"), pk=pk, advertiser=advertiser)

    if campaign.status != Campaign.Status.APPROVED:
        messages.error(request, "Only approved campaigns can be paid for.")
        return redirect("advertiser:campaign_detail", pk=pk)
    
    try:
        from payments.services import initialize_campaign_payment
        paystack_data = initialize_campaign_payment(campaign)

    except ValidationError as e:
        messages.error(request, str(e))
        return redirect("advertiser:campaign_detail", pk=pk)
    
    authorization_url = paystack_data.get("authorization_url")
    if not authorization_url:
        messages.error(request, "Could not initialize payment. Please try again.")
        return redirect("advertiser:campaign_detail", pk=pk)
    
    # Redirect advertiser to Paystack's hosted checkout
    return redirect(authorization_url)