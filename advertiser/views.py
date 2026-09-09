from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db.models import Sum, Q, Prefetch
from django.db.models.functions import TruncMonth, TruncYear
from django.utils import timezone
from datetime import timedelta
from datetime import datetime
import json
from .forms import AdvertiserProfileForm, MediaUploadForm, CampaignForm
from advertiser.decorators import advertiser_required
from .models import Advertiser, Campaign, CampaignSlot, Media
from device.models import Billboard, PlaybackLog
from django.db import transaction
from .tasks import _notify_campaign_submitted
from django.core.paginator import Paginator
from scheduling.models import TimeSlot
from security.models import CustomUser
from decimal import Decimal, InvalidOperation
import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

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

def _display_validation_error(request, e):
    if hasattr(e, "message_dict"):
        for field, errors in e.message_dict.items():
            for error in errors:
                if field in ("__all__", "billboard"):
                    messages.error(request, error)
                else:
                    label = field.replace("_", " ").capitalize()
                    messages.error(request, f"{label}: {error}")
    elif hasattr(e, "messages"):
        for error in e.messages:
            messages.error(request, error)
    else:
        messages.error(request, str(e))

@login_required(login_url='security:login')
def advertiser_create_profile(request):
    if request.user.role != CustomUser.UserRole.ADVERTISER:
        messages.error(request, "This account is not registered as an advertiser.")
        return redirect("security:login")
    
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
        form = AdvertiserProfileForm(instance=advertiser)
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

    # Build a set of media IDs that have active campaigns right now
    active_media_ids = set(
        Campaign.objects.filter(advertiser=advertiser,status=Campaign.Status.ACTIVE,end_date__gte=today,).values_list("media_id", flat=True))

    completed_media_ids = set(
        Campaign.objects.filter(
            advertiser=advertiser,
            status=Campaign.Status.COMPLETED,
        ).values_list("media_id", flat=True)
    )

    # Filter media based on tab selection ('all', 'image', or 'video')
    media_type = request.GET.get("type", "all")
    media_files_qs = Media.objects.filter(advertiser=advertiser)

    if media_type in ["image", "video"]:
        media_files_qs = media_files_qs.filter(media_type=media_type)

    media_files_qs = media_files_qs.order_by("-created_at")

    # Pagination setup
    paginator = Paginator(media_files_qs, 12)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    context = {
        "media_files": page_obj.object_list,
        "page_obj": page_obj,
        "active_media_ids": active_media_ids,
        "completed_media_ids": completed_media_ids,
        "current_type": media_type,
        "today": today,
    }

    if request.headers.get("HX-Request"):
        return render(request, "advertiser/partials/media_grid.html", context)

    return render(request, "advertiser/media_library.html", context)
 
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
                return redirect("advertiser:media_library")
            except ValidationError as e:
                error_dict = (e.message_dict if hasattr(e, "message_dict") else {"__all__": e.messages})
                for field, errors in error_dict.items():
                    for error in errors:
                        if field == "__all__":
                            messages.warning(request, error)
                        else:
                            messages.error(request, error)
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    if field == "__all__":
                        messages.warning(request, error)
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

@login_required(login_url="security:login")
@advertiser_required
def media_preview(request, pk):
    """
    GET /advertiser/media/<pk>/preview/

    HTMX-only endpoint. Renders the modal's inner content (preview pane +
    details sidebar) for a single media item. Replaces the old JS function
    that built this markup client-side from data passed through onclick().
    """
    advertiser = _get_advertiser(request)
    media = get_object_or_404(Media, pk=pk, advertiser=advertiser)
    return render(request, "advertiser/partials/media_preview_modal.html", {"media": media})

# browse billboards
@login_required(login_url="security:login")
@advertiser_required
def browse_billboards(request):
    billboards = Billboard.bookable().select_related("ad_manager").order_by("name")
    search_query = request.GET.get("q", "").strip()
    screen_type = request.GET.get("screen_type", "").strip()
    max_price = request.GET.get("max_price", "").strip()
    country = request.GET.get("country", "").strip()
    state = request.GET.get("state", "").strip()
    lat = request.GET.get("lat", "").strip()
    lng = request.GET.get("lng", "").strip()
 
    if search_query:
        billboards = billboards.filter(
            Q(name__icontains=search_query)
            | Q(location_name__icontains=search_query)
            | Q(state__icontains=search_query)
            | Q(country__icontains=search_query)
        )
    if screen_type:
        billboards = billboards.filter(screen_type=screen_type)
    if max_price:
        try:
            billboards = billboards.filter(price_per_slot__lte=Decimal(max_price))
        except (InvalidOperation, ValueError):
            pass
    if country:
        billboards = billboards.filter(country__icontains=country)
    if state:
        billboards = billboards.filter(state__icontains=state)
    if lat and lng:
        try:
            lat_f, lng_f = float(lat), float(lng)
            billboards = billboards.filter(
                latitude__gte=lat_f - 0.1, latitude__lte=lat_f + 0.1,
                longitude__gte=lng_f - 0.1, longitude__lte=lng_f + 0.1,
            )
        except ValueError:
            pass
 
    screen_type_choices = Billboard.ScreenType.choices
    context = {
        "billboards": billboards,
        "screen_type_choices": screen_type_choices,
        "search_query": search_query,
        "selected_screen_type": screen_type,
        "max_price": max_price,
        "country": country,
        "state": state,
        "lat": lat,
        "lng": lng,
    }
 
    if request.headers.get("HX-Request"):
        return render(request, "advertiser/partials/browse_billboards_content.html", context)
 
    return render(request, "advertiser/browse_billboards.html", context)

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
        return render(request, "advertiser/partials/campaign_table.html", context)

    return render(request, "advertiser/campaign_list.html", context)

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

        try:
            max_concurrent_positions = bb.capacity.max_concurrent_positions
        except ObjectDoesNotExist:
            max_concurrent_positions = None  # no capacity configured yet — form skips the live seat check for this billboard

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
            "max_concurrent_positions": max_concurrent_positions,
        }
    return json.dumps(result)

@login_required(login_url="security:login")
@advertiser_required
def campaign_create(request):
    advertiser = _get_advertiser(request)
    available_billboards = Billboard.bookable().order_by("name")
    # ?billboard=<pk> from the "Book" button on browse_billboards
    preselected_billboard = request.GET.get("billboard", "")

    if request.method == "POST":
        form = CampaignForm(advertiser, request.POST)
        if form.is_valid():
            billboard_id = request.POST.get("billboard", "").strip()
            try:
                slots_per_day = int(request.POST.get("slots_per_day", 1) or 1)
            except (TypeError, ValueError):
                slots_per_day = 1
            if slots_per_day < 1:
                messages.error(request, "Slots per day must be at least 1.")
                return redirect(request.path)

            if not billboard_id:
                messages.error(request, "Please select a billboard.")
            else:
                billboard = get_object_or_404(Billboard, pk=billboard_id, id__in=Billboard.bookable().values("id"))
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
                    _display_validation_error(request, e)
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
def campaign_select_dates(request, pk):
    """
    GET: Displays the editable daypart availability heatmap and start-date picker.
    POST: Verifies full date range capacity and creates TimeSlots via confirm_campaign_dates().
    Daypart is editable here so advertisers can resolve schedule conflicts without recreating campaigns.
    """
    from advertiser.services import confirm_campaign_dates
    from scheduling.models import ScheduleGenerationError
   
    advertiser = _get_advertiser(request)
    campaign = get_object_or_404(Campaign.objects.prefetch_related("campaign_slots__billboard__capacity"),pk=pk, advertiser=advertiser,)
    if campaign.status == Campaign.Status.APPROVAL_EXPIRED:
        messages.warning(request, "This campaign's approval window has expired. Please resubmit for review.")
        return redirect("advertiser:campaign_detail", pk=pk)
    
    if campaign.status != Campaign.Status.APPROVED:
        messages.info(request, "This campaign doesn't need date selection right now.")
        return redirect("advertiser:campaign_detail", pk=pk)
           
    if campaign.start_date:
        messages.info(request, "Dates have already been confirmed for this campaign.")
        return redirect("advertiser:campaign_detail", pk=pk)
    
    today = timezone.now().date() # current date
 
    if request.method == "POST":
        start_date_str = request.POST.get("start_date", "").strip()
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        except ValueError:
            messages.error(request, "Please select a valid start date.")
            return redirect("advertiser:campaign_select_dates", pk=pk)
 
        daily_start_time = daily_end_time = None
        raw_start = request.POST.get("daily_start_time", "").strip()
        raw_end = request.POST.get("daily_end_time", "").strip()
        if raw_start and raw_end:
            try:
                daily_start_time = datetime.strptime(raw_start, "%H:%M").time()
                daily_end_time = datetime.strptime(raw_end, "%H:%M").time()
            except ValueError:
                messages.error(request, "Please enter a valid daily time window.")
                return redirect("advertiser:campaign_select_dates", pk=pk)
 
        try:
            confirm_campaign_dates(
                campaign, start_date=start_date,
                daily_start_time=daily_start_time, daily_end_time=daily_end_time,
            )
            messages.success(
                request,
                f"Dates confirmed: {campaign.start_date.strftime('%b %d')} — "
                f"{campaign.end_date.strftime('%b %d, %Y')}. Proceed to payment below."
            )
            return redirect("advertiser:campaign_detail", pk=pk)
        except ScheduleGenerationError as e:
            conflict_dates = sorted(set(d.strftime("%b %d") for _, d in e.conflicts))
            messages.error(
                request,
                f"{e} Unavailable dates: {', '.join(conflict_dates[:8])}"
                + ("..." if len(conflict_dates) > 8 else "")
            )
        except ValidationError as e:
            messages.error(request, e.message if hasattr(e, "message") else str(e))
 
    slots = list(campaign.campaign_slots.select_related("billboard__capacity").all())
 
    return render(request, "advertiser/campaign_select_dates.html", {
        "campaign": campaign,
        "slots": slots,
        "min_date": (today + timedelta(days=1)).strftime("%Y-%m-%d"),
        "billboard_pk": str(slots[0].billboard_id) if slots else None,
    })
@login_required(login_url="security:login")
@advertiser_required
def campaign_run_again(request, pk):
    """
    POST /advertiser/campaigns/<pk>/run-again/

    Creates a new DRAFT campaign copying media, billboard, duration, daily
    hours, and budget from a completed campaign. Dates are NEVER copied 
    they don't exist on the new draft. It goes through the full approval +
    date-selection flow again, exactly like any new campaign.

    Daily hours are clamped to fit the billboard's CURRENT operating hours,
    since those can change between when the original campaign ran and now.
    If there's no overlap at all, the advertiser is told to create a fresh
    campaign with new hours instead.
    """
    if request.method != "POST":
        return redirect("advertiser:campaign_detail", pk=pk)

    advertiser = _get_advertiser(request)
    original = get_object_or_404(
        Campaign.objects.prefetch_related("campaign_slots__billboard"),
        pk=pk,
        advertiser=advertiser,
    )

    # Guard only completed campaigns can be re-run
    if original.status != Campaign.Status.COMPLETED:
        messages.error(request, "Only completed campaigns can be run again.")
        return redirect("advertiser:campaign_detail", pk=pk)

    # Get the original billboard slot
    original_slot = original.campaign_slots.select_related("billboard").first()
    if not original_slot:
        messages.error(
            request, "Cannot re-run this campaign — no billboard slot found."
        )
        return redirect("advertiser:campaign_detail", pk=pk)

    billboard = original_slot.billboard

    # Check billboard is still available
    if not Billboard.bookable().filter(pk=billboard.pk).exists():
        messages.error(
            request,
            f"'{billboard.name}' is no longer available for booking "
            "(it may be unpaired or disabled). "
            "Please create a new campaign and select a different billboard."
        )
        return redirect("advertiser:campaign_detail", pk=pk)

    # Check media is still approved
    if original.media and original.media.status not in (
        original.media.Status.ADMIN_APPROVED,
        original.media.Status.FULLY_APPROVED,
    ):
        messages.error(
            request,
            f"The media '{original.media.title}' is no longer approved. "
            "Please create a new campaign and select approved media."
        )
        return redirect("advertiser:campaign_detail", pk=pk)

    bb_start = billboard.operating_hours_start
    bb_end = billboard.operating_hours_end

    daily_start = max(original.daily_start_time, bb_start)
    daily_end = min(original.daily_end_time, bb_end)

    if daily_start >= daily_end:
        messages.error(
            request,
            f"'{billboard.name}''s operating hours have changed "
            f"({bb_start.strftime('%I:%M %p')}–{bb_end.strftime('%I:%M %p')}) "
            f"and no longer overlap with this campaign's original schedule "
            f"({original.daily_start_time.strftime('%I:%M %p')}–"
            f"{original.daily_end_time.strftime('%I:%M %p')}). "
            "Please create a new campaign with fresh daily hours."
        )
        return redirect("advertiser:campaign_detail", pk=pk)

    hours_were_clamped = (
        daily_start != original.daily_start_time
        or daily_end != original.daily_end_time
    )

    try:
        with transaction.atomic():
            new_campaign = Campaign(
                advertiser=advertiser,
                name=original.name,
                media=original.media,
                duration_days=original.duration_days,
                daily_start_time=daily_start,
                daily_end_time=daily_end,
                budget=original.budget,
                status=Campaign.Status.DRAFT,
            )
            new_campaign.save()

            CampaignSlot.objects.create(
                campaign=new_campaign,
                billboard=billboard,
                slots_per_day=original_slot.slots_per_day,
            )
            new_campaign.sync_estimated_price()

        if hours_were_clamped:
            messages.warning(
                request,
                f"New draft created from '{original.name}'. Note: "
                f"'{billboard.name}''s operating hours have changed, so your "
                f"daily window was adjusted to "
                f"{daily_start.strftime('%I:%M %p')}–{daily_end.strftime('%I:%M %p')} "
                f"to fit. Review before submitting."
            )
        else:
            messages.info(
                request,
                f"New draft created from '{original.name}'. Submit it for "
                "review when you're ready — you'll pick fresh dates once "
                "it's approved."
            )

        return redirect("advertiser:campaign_detail", pk=new_campaign.pk)

    except Exception:
        logger.exception("campaign_run_again failed for campaign %s", pk)
        messages.error(request, "Could not create the new campaign. Please try again.")
        return redirect("advertiser:campaign_detail", pk=pk)

@login_required(login_url="security:login")
@advertiser_required        
def campaign_edit(request, pk):
    advertiser = _get_advertiser(request) 
    campaign = get_object_or_404(Campaign, pk=pk, advertiser=advertiser)

    if campaign.status not in [Campaign.Status.DRAFT, Campaign.Status.REJECTED]:
        messages.error(request, "This campaign can't be edited in its current status.")
        return redirect("advertiser:campaign_detail", pk=campaign.pk)
    
    available_billboards = Billboard.bookable().order_by("name")

    # Existing slot — one billboard per campaign in current UI
    existing_slot = campaign.campaign_slots.select_related("billboard").first()

    if request.method == "POST": 
        form = CampaignForm(advertiser, request.POST, instance=campaign)
        if form.is_valid():
            billboard_id = request.POST.get("billboard", "").strip()
            try:
                slots_per_day = int(request.POST.get("slots_per_day", 1) or 1)
            except (TypeError, ValueError):
                slots_per_day = 1
            if slots_per_day < 1:
                messages.error(request, "Slots per day must be at least 1.")
                return redirect(request.path)

            if not billboard_id:
                messages.error(request, "Please select a billboard.")
            else:
                billboard = get_object_or_404(Billboard, pk=billboard_id, id__in=Billboard.bookable().values("id"))
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
                    _display_validation_error(request, e)
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
        "is_edit": True,
    }
    return render(request, "advertiser/campaign_edit.html", context)

# A campaign is "active" for its whole data range that does not mean it's airing this exact second, only that
# today falls within it and payment/approval cleared. Checked per-billboard (not once globally) since a campaign can run
# on billboards in different timezones, each with its own local "is it currently within the daypart" answer. 
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
        payment = getattr(campaign, "payment", None)
        if payment and payment.status == "pending":
            from payments.services import sync_pending_payment
            previous_status = payment.status
            payment = sync_pending_payment(payment)
            campaign.refresh_from_db()
            if payment.status == "completed" and previous_status != "completed":
                messages.success(request, "Payment confirmed! Your campaign is now active.")
            elif payment.status == "failed" and previous_status != "failed":
                messages.warning(request, "That payment attempt wasn't completed. You can try again below.") 
    except Exception:
        payment = getattr(campaign, "payment", None)
    slots = campaign.campaign_slots.select_related("billboard").all()

    now = timezone.now()
    on_air_billboards = []
    if campaign.status == Campaign.Status.ACTIVE:
        for slot in slots:
            try:
                billboard_now = now.astimezone(ZoneInfo(slot.billboard.timezone))
            except (ValueError, TypeError, ZoneInfoNotFoundError):
                logging.warning(
                    "Invalid timezone %r on billboard %s (id=%s) — falling back to UTC",
                    slot.billboard.timezone, slot.billboard.name, slot.billboard_id,
                )
                billboard_now = now
            start_t, end_t = campaign.daily_start_time, campaign.daily_end_time
            if start_t < end_t:  
                in_window = start_t <= billboard_now.time() < end_t
            elif start_t > end_t:
                # wraps past midnight (e.g 22:00-02:00)
                in_window = billboard_now.time() >= start_t or billboard_now.time() < end_t
            else: 
                in_window = False # identical start/end already rejected at creation
            if campaign.start_date <= billboard_now.date() <= campaign.end_date and in_window:
                on_air_billboards.append(slot.billboard.name)
    is_on_air_now = bool(on_air_billboards)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "submit":
            try:
                campaign.submit_for_approval()
                # _notify_campaign_submitted.delay(str(campaign.id)) # for prod
                # _notify_campaign_submitted(str(campaign.id))
                transaction.on_commit(lambda: _notify_campaign_submitted.delay(str(campaign.id)))
                messages.success(request, "Campaign submitted for review.")
            except ValidationError as e:
                _display_validation_error(request, e)
        elif action == "cancel":
            try:
                campaign.cancel()
                messages.success(request, f"'{campaign.name}' has been cancelled.")
                return redirect("advertiser:campaign_list")
            except ValidationError as e:
                _display_validation_error(request, e)
        return redirect("advertiser:campaign_detail", pk=campaign.pk)

    return render(request, "advertiser/campaign_detail.html", {
        "campaign": campaign,
        "slots": slots,
        "payment": payment,
        "is_on_air_now": is_on_air_now, 
        "on_air_billboards": on_air_billboards,
       
    })


@login_required(login_url="security:login")
@advertiser_required
def campaign_playback_log(request, pk):
    """
    Slot-by-slot reconciliation for the advertiser: every TimeSlot scheduled
    for this campaign, matched against whether a PlaybackLog confirms it
    actually played on the ad manager's billboard.
    """
    advertiser = _get_advertiser(request)
    campaign = get_object_or_404(Campaign, pk=pk, advertiser=advertiser)
    time_slots = (
        TimeSlot.objects.filter(campaign=campaign)
        .select_related("billboard")
        .prefetch_related(
            Prefetch(
                "playback_logs",
                queryset=PlaybackLog.objects.filter(completed=True).order_by("started_at"),
                to_attr="confirmed_logs",
            )
        )
        .order_by("date", "play_order")
    )
    rows = []
    for ts in time_slots:
        log = ts.confirmed_logs[0] if ts.confirmed_logs else None
        try:
            billboard_now = timezone.now().astimezone(ZoneInfo(ts.billboard.timezone))
        except (ValueError, TypeError, ZoneInfoNotFoundError):
            logger.warning(
                "Invalid timezone %r on billboard %s (id=%s) — falling back to UTC",
                ts.billboard.timezone, ts.billboard.name, ts.billboard_id,
            )
            billboard_now = timezone.now()
        start_t, end_t = campaign.daily_start_time, campaign.daily_end_time
        close_date = ts.date + timedelta(days=1) if end_t <= start_t else ts.date
        close_at = datetime.combine(close_date, end_t, tzinfo=billboard_now.tzinfo)
        if log:
            state = "confirmed"
        elif billboard_now < close_at:
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
        return render(request, "advertiser/partials/campaign_playback_log_table.html", context)
    return render(request, "advertiser/campaign_playback_log.html", context)

@login_required(login_url="security:login")
@advertiser_required
def campaign_status_fragment(request, pk):
    """
    GET /advertiser/campaigns/<pk>/status/
 
    HTMX polling endpoint. Returns just the banner HTML fragment.
    Called every 8 seconds by HTMX on the campaign detail page.
 
    Auto-verifies pending payments with Paystack on each poll.
    Stops polling once payment is completed or campaign is active/failed.
    """
    advertiser = _get_advertiser(request)
    campaign = get_object_or_404(Campaign.objects.select_related("media", "advertiser", "payment"),pk=pk,advertiser=advertiser,)
 
    payment = None
    try:
        payment = getattr(campaign, "payment", None)
        # Auto-sync pending payment against Paystack's live status on each poll
        if payment and payment.status == "pending":
            from payments.services import sync_pending_payment
            payment = sync_pending_payment(payment)
            campaign.refresh_from_db()
    except Exception:
        payment = getattr(campaign, "payment", None)
 
    return render(request, "advertiser/partials/campaign_status_banner.html", {
        "campaign": campaign,
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

    Initiates a Paystack payment for an APPROVED campaign that has confirmed
    dates. Creates a CampaignPayment record (PENDING) then redirects the
    advertiser to Paystack's hosted checkout page.

    On return from Paystack, the advertiser lands back on campaign_detail.
    The actual mark_completed() happens via the Paystack webhook — NOT here.

    Guards:
    - Campaign must belong to this advertiser
    - Campaign must be APPROVED
    - Campaign must have confirmed dates (start_date set)
    - No active PENDING or COMPLETED payment already exists
    """
    if request.method != "POST":
        return redirect("advertiser:campaign_detail", pk=pk)

    advertiser = _get_advertiser(request)
    campaign = get_object_or_404(
        Campaign.objects.select_related("advertiser", "payment"), pk=pk, advertiser=advertiser
    )

    if campaign.status != Campaign.Status.APPROVED:
        messages.warning(request, "Only approved campaigns can be paid for.")
        return redirect("advertiser:campaign_detail", pk=pk)

    if not campaign.start_date:
        messages.error(request, "Please select your campaign dates before paying.")
        return redirect("advertiser:campaign_select_dates", pk=pk)

    try:
        from payments.services import initialize_campaign_payment
        paystack_data = initialize_campaign_payment(campaign)

    except ValidationError as e:
        messages.error(request, " ".join(e.messages))
        return redirect("advertiser:campaign_detail", pk=pk)

    authorization_url = paystack_data.get("authorization_url")
    if not authorization_url:
        messages.error(request, "Could not initialize payment. Please try again.")
        return redirect("advertiser:campaign_detail", pk=pk)

    # Redirect advertiser to Paystack's hosted checkout
    return redirect(authorization_url)