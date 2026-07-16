from celery import shared_task
from .models import Campaign
import logging
logger = logging.getLogger("advertiser.services")
from adverseproject.emails import send_adverse_email
from django.conf import settings

@shared_task(bind=True, max_retries=3)
def _notify_campaign_submitted(self, campaign_id):
    # Email advertiser when their campaign is submitted for review.
    try:

        campaign = Campaign.objects.select_related("advertiser__user",).get(id=campaign_id)

        send_adverse_email(
            template="campaign_submitted",
            to=campaign.advertiser.user.email,
            context={
                    "advertiser_name": campaign.advertiser.user.get_full_name()
                        or campaign.advertiser.user.email,
                    "campaign_name": campaign.name,
                    "start_date": campaign.start_date.strftime("%b %d, %Y"),
                    "end_date": campaign.end_date.strftime("%b %d, %Y"),
                    "campaign_url": f"{_site_url()}/advertiser/campaigns/{campaign.id}/",
                },
        )
        logger.info("Submission notification sent for campaign %s", campaign_id)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)

"""
@shared_task(bind=True, max_retries=3)
def _notify_campaign_approved(self, campaign_id):
    # Send approval email to advertiser. Retries up to 3 times if email fails.
    
    try:
        campaign = Campaign.objects.select_related(
            "advertiser__user",
            "campaign_slots__billboard",
        ).get(id=campaign_id)

        first_slot = campaign.campaign_slots.select_related("billboard").first()
        billboard_name = first_slot.billboard.name if first_slot else "Your billboard"
        
        # Get the campaign price
        amount = getattr(campaign, "actual_price", None) or getattr(campaign, "total_price", "")

        send_adverse_email(
            template="campaign_approved",
            to=campaign.advertiser.user.email,
            context={
                "advertiser_name": campaign.advertiser.user.get_full_name()
                    or campaign.advertiser.user.email,
                "campaign_name": campaign.name,
                "start_date": campaign.start_date.strftime("%b %d, %Y"),
                "end_date": campaign.end_date.strftime("%b %d, %Y"),
                "billboard_name": billboard_name,
                "amount": f"{amount:,.2f}" if amount else "—",
                "payment_url": f"{_site_url()}/advertiser/campaigns/{campaign.id}/",
                "campaign_url": f"{_site_url()}/advertiser/campaigns/{campaign.id}/",
            },
        )
        logger.info("Approval notification sent for campaign %s", campaign_id)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)
"""

@shared_task(bind=True, max_retries=3)
def _notify_campaign_approved(self, campaign_id):
    try:
        from adverseproject.emails import send_adverse_email

        campaign = Campaign.objects.select_related(
            "advertiser__user",
        ).prefetch_related(
            "campaign_slots__billboard",
        ).get(id=campaign_id)

        first_slot = campaign.campaign_slots.select_related("billboard").first()
        billboard_name = first_slot.billboard.name if first_slot else "Your billboard"

        # Safely get amount — try all possible field names
        amount = (
            getattr(campaign, "actual_price", None)
            or getattr(campaign, "total_price", None)
            or getattr(campaign, "budget", None)
            or 0
        )

        send_adverse_email(
            template="campaign_approved",
            to=campaign.advertiser.user.email,
            context={
                "advertiser_name": campaign.advertiser.user.get_full_name()
                    or campaign.advertiser.user.email,
                "campaign_name": campaign.name,
                "start_date": campaign.start_date.strftime("%b %d, %Y"),
                "end_date": campaign.end_date.strftime("%b %d, %Y"),
                "billboard_name": billboard_name,
                "amount": f"{amount:,.2f}" if amount else "Contact support",
                "payment_url": f"{_site_url()}/advertiser/campaigns/{campaign.id}/",
                "campaign_url": f"{_site_url()}/advertiser/campaigns/{campaign.id}/",
            },
        )
        logger.info("Approval notification sent for campaign %s", campaign_id)
    except Exception as exc:
        logger.exception("_notify_campaign_approved failed: %s", exc)
        raise self.retry(exc=exc, countdown=60)

@shared_task(bind=True, max_retries=3)
def _notify_campaign_rejected(self, campaign_id, reason):
    # Email advertiser when their campaign is rejected
    try:
        campaign = Campaign.objects.select_related(
            "advertiser__user"
        ).get(id=campaign_id)

        send_adverse_email(
            template="campaign_rejected",
            to=campaign.advertiser.user.email,
            context={
                "advertiser_name": campaign.advertiser.user.get_full_name()
                    or campaign.advertiser.user.email,
                "campaign_name": campaign.name,
                "reason": reason or "No reason provided.",
                "rejected_by": "AdVerse team",
                "campaign_url": f"{_site_url()}/advertiser/campaigns/{campaign.id}/",
            },
        )
        logger.info("Rejection notification sent for campaign %s", campaign_id)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)
    
@shared_task(bind=True, max_retries=3)
def _notify_forwarded_to_manager(self, campaign_id):
    # Email each ad manager whose billboard is in this campaign
    try:
        campaign = Campaign.objects.prefetch_related(
            "campaign_slots__billboard__ad_manager__user"
        ).get(id=campaign_id)
        
        # notify each ad manager whose billboard is in this campaign
        amount = getattr(campaign, "actual_price", None) or getattr(campaign, "total_price", 0)
        manager_amount = float(amount) * 0.90 if amount else 0

        for slot in campaign.campaign_slots.all():
            billboard = slot.billboard
            manager = billboard.ad_manager
            if not manager or not manager.user or not manager.user.email:
                continue
 
            send_adverse_email(
                template="new_campaign_request",
                to=manager.user.email,
                context={
                    "manager_name": manager.user.get_full_name() or manager.user.email,
                    "campaign_name": campaign.name,
                    "advertiser_name": campaign.advertiser.user.get_full_name()
                        or campaign.advertiser.user.email,
                    "billboard_name": billboard.name,
                    "billboard_location": billboard.location_name,
                    "start_date": campaign.start_date.strftime("%b %d, %Y"),
                    "end_date": campaign.end_date.strftime("%b %d, %Y"),
                    "daily_start": campaign.daily_start_time.strftime("%H:%M"),
                    "daily_end": campaign.daily_end_time.strftime("%H:%M"),
                    "manager_amount": f"{manager_amount:,.2f}",
                    "review_url": f"{_site_url()}/admanager/campaigns/{campaign.id}/",
                },
            )
 
        logger.info("Manager notification sent for campaign %s", campaign_id)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)

@shared_task(bind=True, max_retries=3)
def _notify_campaign_completed(self, campaign_id):
    """Email advertiser when their campaign ends."""
    try:
        from adverseproject.emails import send_adverse_email
 
        campaign = Campaign.objects.select_related(
            "advertiser__user",
            "campaign_slots__billboard",
        ).get(id=campaign_id)
 
        first_slot = campaign.campaign_slots.select_related("billboard").first()
        billboard_name = first_slot.billboard.name if first_slot else "Your billboard"
 
        duration_days = (campaign.end_date - campaign.start_date).days + 1
 
        send_adverse_email(
            template="campaign_completed",
            to=campaign.advertiser.user.email,
            context={
                "advertiser_name": campaign.advertiser.user.get_full_name()
                    or campaign.advertiser.user.email,
                "campaign_name": campaign.name,
                "start_date": campaign.start_date.strftime("%b %d, %Y"),
                "end_date": campaign.end_date.strftime("%b %d, %Y"),
                "billboard_name": billboard_name,
                "duration_days": duration_days,
                "dashboard_url": f"{_site_url()}/advertiser/campaigns/",
            },
        )
        logger.info("Completion notification sent for campaign %s", campaign_id)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)
    
# helper
def _site_url() -> str: 
    return getattr(settings, "SITE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")