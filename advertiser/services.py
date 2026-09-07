from django.db import transaction
import logging
from scheduling.models import generate_schedule, ScheduleGenerationError
from .tasks import _notify_campaign_approved, _notify_campaign_rejected, _notify_forwarded_to_manager, _notify_campaign_submitted, _notify_campaign_completed
# from payments.models import process_campaign_payment

logger = logging.getLogger("advertiser.services")

@transaction.atomic
def approve_campaign_by_manager(campaign, manager_user):
    """
    Single entry point for ad manager campaign approval.

    What happens here:
    1. Campaign status → APPROVED, approved_at stamped (starts 7-day expiry clock)
    2. Media status    → FULLY_APPROVED
    3. Notification    → advertiser told to pick real dates next

    Scheduling (TimeSlot generation) does NOT happen here anymore — it only
    happens once the advertiser confirms real calendar dates via
    confirm_campaign_dates(), since dates aren't known at approval time.
    """
    campaign.manager_approve(manager_user)

    # queue notifications (outside transaction is fine,
    # Celery task runs after commit so campaign is visible in DB)
    # _notify_campaign_approved.delay(str(campaign.id))
    transaction.on_commit(lambda: _notify_campaign_approved.delay(str(campaign.id)))
    return {
    "campaign_id": str(campaign.id),
    "status": campaign.status,
}

@transaction.atomic
def confirm_campaign_dates(campaign, start_date, daily_start_time=None, daily_end_time=None):
    """
    daily_start_time/daily_end_time are optional overrides — see
    Campaign.confirm_dates() docstring for why this is safe to allow here
    (ad manager approval covers content + billboard, not the exact hours).
    When given, generate_schedule() below picks them up automatically since
    it reads straight from campaign.daily_start_time/daily_end_time, which
    confirm_dates() has already updated by the time we get here.
    """
    campaign.confirm_dates(start_date, daily_start_time=daily_start_time, daily_end_time=daily_end_time)
    slots_created = generate_schedule(campaign)

    logger.info(
        "Campaign %s dates confirmed: %s — %s (%d slots created)",
        campaign.id, campaign.start_date, campaign.end_date, slots_created,
    )
    return {
        "campaign_id": str(campaign.id),
        "start_date": campaign.start_date,
        "end_date": campaign.end_date,
        "slots_created": slots_created,
    }

@transaction.atomic
def reject_campaign(campaign, reviewer, reason):
    """
    Works for both admin rejection and ad manager rejection.
    Determines the stage automatically from campaign status.
    """
    campaign.reject(reviewer=reviewer, reason=reason)
    _notify_campaign_rejected.delay(str(campaign.id), reason)
    return campaign

@transaction.atomic  
def admin_forward_campaign(campaign, admin_user):
    """
    Global Tech Admin forwards campaign to ad manager for review.
    PENDING_ADMIN_REVIEW → PENDING_MANAGER_REVIEW
    """
    campaign.admin_forward_to_manager(admin_user)
    _notify_forwarded_to_manager.delay(str(campaign.id))
    return campaign
