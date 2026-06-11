from celery import shared_task
from django.utils import timezone
from advertiser.models import Campaign
import logging

logger = logging.getLogger("scheduling.tasks")

@shared_task
def activate_due_campaigns():
    """
    Finds APPROVED campaigns whose start_date is today or in the past,
    and moves them to ACTIVE.
    """
    today = timezone.now().date()
    due_campaigns = Campaign.objects.filter(
        status=Campaign.Status.APPROVED,
        start_date__lte=today
    )
    
    count = 0
    for campaign in due_campaigns:
        # Assuming your Campaign model has an activate method
        if hasattr(campaign, 'activate'):
            campaign.activate()
        else:
            campaign.status = Campaign.Status.ACTIVE
            campaign.save()
        count += 1
        
    logger.info(f"Automated check: Activated {count} campaigns due for {today}.")
    return f"Activated {count} campaigns."


@shared_task
def expire_old_campaigns():
    """
    Finds ACTIVE campaigns whose end_date was yesterday or earlier,
    and moves them to EXPIRED.
    """
    today = timezone.now().date()
    expired_campaigns = Campaign.objects.filter(
        status=Campaign.Status.ACTIVE,
        end_date__lt=today
    )
    
    count = 0
    for campaign in expired_campaigns:
        if hasattr(campaign, 'expire'):
            campaign.expire()
        else:
            campaign.status = Campaign.Status.EXPIRED
            campaign.save()
        count += 1
        
    logger.info(f"Automated check: Expired {count} campaigns older than {today}.")
    return f"Expired {count} campaigns."
