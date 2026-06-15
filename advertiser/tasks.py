from celery import shared_task
from .models import Campaign
import logging
logger = logging.getLogger("advertiser.services")

@shared_task(bind=True, max_retries=3)
def _notify_campaign_approved(self, campaign_id):
    """
    Send approval email to advertiser.
    Retries up to 3 times if email fails.
    """
    try:
        campaign = Campaign.objects.select_related(
            "advertiser__user"
        ).get(id=campaign_id)
        # send_mail(....to be continued)
        logger.info(f"Approval notification sent for campaign {campaign_id}")
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=3)
def _notify_campaign_rejected(self, campaign_id, reason):
    try:
        campaign = Campaign.objects.select_related(
            "advertiser__user"
        ).get(id=campaign_id)
        # send_mail(...)
        logger.info(f"Rejection notification sent for campaign {campaign_id}")
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)
    
@shared_task(bind=True, max_retries=3)
def _notify_forwarded_to_manager(self, campaign_id):
    try:
        campaign = Campaign.objects.prefetch_related(
            "campaign_slots__billboard__ad_manager__user"
        ).get(id=campaign_id)
        # notify each ad manager whose billboard is in this campaign
        logger.info(f"Manager notification sent for campaign {campaign_id}")
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)