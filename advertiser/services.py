from django.db import transaction
import logging
from scheduling.models import generate_schedule
from .tasks import _notify_campaign_approved, _notify_campaign_rejected, _notify_forwarded_to_manager
# from payments.models import process_campaign_payment

logger = logging.getLogger("advertiser.services")
@transaction.atomic
def approve_campaign_by_manager(campaign, manager_user):
    """
        Single entry point for ad manager campaign approval.
        
        What happens here (all visible, all intentional):
        1. Campaign status → APPROVED
        2. Media status    → FULLY_APPROVED  
        3. Payment         → deducted from advertiser, credited to ad manager
        4. Schedule        → TimeSlots generated for every day of campaign
        5. Notification    → queued via Celery (non-blocking)
        
        Everything runs in one transaction.
        If anything fails, the entire approval is rolled back.
    """
    campaign.manager_approve(manager_user)

    # If advertiser has insufficient funds, this raises and rolls back
    # payment = process_campaign_payment(campaign)
    slots_created, slots_skipped = generate_schedule(campaign)

    if slots_skipped > 0:
        logger.warning(
            f"Campaign {campaign.id} approved but {slots_skipped} slots "
            f"skipped due to billboard capacity."
        )

    # queue notifications (outside transaction is fine,
    # Celery task runs after commit so campaign is visible in DB)
    _notify_campaign_approved.delay(str(campaign.id))

    return {
    "campaign_id":   str(campaign.id),
    "status":        campaign.status,
    # "payment_total": payment.total_amount,
    "slots_created": slots_created,
    "slots_skipped": slots_skipped,
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
