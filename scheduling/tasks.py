from celery import shared_task
from django.utils import timezone
from advertiser.models import Campaign
import logging

logger = logging.getLogger("scheduling.tasks")


@shared_task
def activate_due_campaigns():
    """
    Finds APPROVED campaigns whose start_date has arrived AND have a completed payment and moves them to ACTIVE

    The payment check is not optional: without it, any approved campaign whose start_date arrives goes live on a billboard whether or not
    the advertiser ever actually paid. Dates get confirmed and Timeslots generated at approval time, independent of payment
    """
    today = timezone.now().date()
    due_campaigns = Campaign.objects.filter(
        status=Campaign.Status.APPROVED,
        start_date__lte=today,
        payment__status="completed",
    )

    # bulk update — single query, skips full_clean() (correct here: this is a
    # routine scheduled transition, not a user-submitted edit needing validation)
    count = due_campaigns.update(status=Campaign.Status.ACTIVE)

    logger.info(f"Automated check: Activated {count} paid campaigns due for {today}.")
    return f"Activated {count} campaigns."


@shared_task
def expire_old_campaigns():
    """
    Finds ACTIVE campaigns whose end_date has passed, moves them to COMPLETED,
    and fires a completion email to each advertiser.
    """
    from advertiser.tasks import _notify_campaign_completed

    today = timezone.now().date()
    expired_campaigns = Campaign.objects.filter(
        status=Campaign.Status.ACTIVE,
        end_date__lt=today,
    ).select_related("advertiser__user")

    count = 0
    for campaign in expired_campaigns:
        campaign.status = Campaign.Status.COMPLETED
        campaign.save(update_fields=["status", "updated_at"])
        _notify_campaign_completed.delay(str(campaign.id))
        count += 1

    logger.info(
        "Automated check: Completed %d campaigns past their end date as of %s.",
        count, today,
    )
    return f"Completed {count} campaigns."

@shared_task
def expire_unconfirmed_approvals():
    """
    Finds APPROVED campaigns with no start_date set (dates never confirmed)
    where approved_at is more than 7 days old. Marks them APPROVAL_EXPIRED
    and notifies the advertiser they need to resubmit.
    """
    from advertiser.tasks import _notify_approval_expired
    from datetime import timedelta

    cutoff = timezone.now() - timedelta(days=7)
    stale = Campaign.objects.filter(
        status=Campaign.Status.APPROVED,
        start_date__isnull=True,
        approved_at__lt=cutoff,
    ).select_related("advertiser__user")

    count = 0
    for campaign in stale:
        campaign.expire_approval()
        _notify_approval_expired.delay(str(campaign.id))
        count += 1

    logger.info("expire_unconfirmed_approvals: %d campaign(s) expired.", count)
    return f"Expired {count} unconfirmed approvals."



"""
@shared_task
def expire_old_campaigns():

    Finds ACTIVE campaigns whose end_date has passed, and moves them to COMPLETED.
    NOTE: Campaign.Status has no EXPIRED value — COMPLETED is the correct
    terminal state for a campaign that ran its full course.
 
    today = timezone.now().date()
    expired_campaigns = Campaign.objects.filter(
        status=Campaign.Status.ACTIVE,
        end_date__lt=today,
    ).select_related("advertiser__user")

    count = expired_campaigns.update(status=Campaign.Status.COMPLETED)

    logger.info(f"Automated check: Completed {count} campaigns past their end date as of {today}.")
    return f"Completed {count} campaigns."
"""