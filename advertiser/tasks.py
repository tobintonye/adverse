from decimal import Decimal
import os
import tempfile
from celery import shared_task
from django.core.files import File
from .models import Campaign, Media
import logging
logger = logging.getLogger("advertiser.services")
from adverseproject.emails import send_adverse_email
from django.conf import settings
from .media_processing import(download_field_file, probe_video, _video_stream, needs_transcode, transcode_video, process_image, MediaProcessingError)

@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def process_media_task(self, media_id):
    """
    Runs after every Media upload/replace. Verifies the file is safe to
    decode on billboard hardware and transcodes it if not. 
    """
    try:
        media = Media.objects.get(id=media_id)
    except Media.DoesNotExist: 
        logger.warning("process_media_task: media %s not found", media_id)
        return 

    media.transcode_status = Media.TrancodeStatus.PROCESSING
    media.save(update_fields=["transcode_status", "updated_at"])

    try: 
        with tempfile.TemporaryDirectory() as tmp_dir:
            original_ext = media.file.name.rsplit(".", 1)[-1].lower()
            input_path = os.path.join(tmp_dir, f"input.{original_ext}")
            download_field_file(media.file, input_path)

            if media.media_type == Media.MediaType.VIDEO:
                probe_data = probe_video(input_path)
                must_transcode, reason = needs_transcode(probe_data)

                if must_transcode:
                    logger.info("Transcoding media %s: %s", media_id, reason)
                    output_path = os.path.join(tmp_dir, f"{media.id}.mp4")
                    transcode_video(input_path, output_path)
                    with open(output_path, "rb") as f:
                        media.processed_file.save(f"{media.id}.mp4", File(f), save=False)
                    final_probe = probe_video(output_path)
                else:
                    final_probe = probe_data

                video_stream = _video_stream(final_probe)
                media.width = int(video_stream.get("width", 0))
                media.height = int(video_stream.get("height", 0))
                media.video_codec = int(video_stream.get("codec_name", ""))
                media.transcode_status = Media.TranscodeStatus.DONE
                media.transcode_error = ""

            else:
                output_path = os.path.join(tmp_dir, f"{media.id}.jpg")
                width, height = process_image(input_path, output_path)
                with open(output_path, "rb") as f:
                    media.processed_file.save(f"{media.id}.jpg", File(f), save=False)
                media.width = width
                media.height = height
                media.transcode_status = Media.TranscodeStatus.DONE
                media.transcode_error = ""
    except MediaProcessingError as exc: 
        logger.warning("Media processing rejected media %s: %s", media_id, exc)
        media.transcode_status = Media.TranscodeStatus.FAILED
        media.transcode_error = str(exc)[:2000]
    except Exception as exc: 
        """
        Transient failures (S3 blip, ffmpeg timeout, worker restart) are worth retrying automatically before giving up
        """
        if self.request.retires < self.max_retries: 
            logger.warning(
                "process_media_task transient failure for %s (attempt %s/%s): %s",
                media_id, self.request.retries + 1, self.max_retries, exc,
            )
            media.transcode_status = Media.TranscodeStatus.PENDING
            media.save(update_fields=["transcode_status", "updated_at"])
            raise self.retry(exc=exc)

        logger.exception("process_media_task exhausted retries for media %s", media_id)
        media.transcode_status = Media.TranscodeStatus.FAILED
        media.transcode_error = f"Failed after {self.max_retries} attempts: {exc}"[:2000]

    media.save(update_fields=[
        "transcode_status", "transcode_error", "processed_file", "width", "height", "video_codec", "updated_at",
    ])

    if media.transcode_status == Media.TrancodeStatus.FAILED:
        _alert_if_paid_campaign_affected(media)

def _alert_if_paid_campaign_affected(media):
    """
    Defensive check, not a currently-reachable path: there is no edit
    endpoint on Media today (MediaDetailView only exposes GET/DELETE, and
    media_delete already blocks deleting anything used by an active/approved
    campaign), and initialize_campaign_payment() refuses to charge for
    unplayable media in the first place. So a paid campaign ending up with
    FAILED media shouldn't currently be possible.

    Left in as a tripwire: if a future Media-replace feature is ever added,
    this is what will catch the gap immediately instead of silently. No
    refund flow exists in this app, so this only logs — there's nothing
    automated to trigger here, just a signal for a human to notice fast.
    """
    affected = media.campaigns.filter(
        payment__status="completed"
    ).values_list("id", flat=True)

    for campaign_id in affected:
        logger.critical(
            "UNEXPECTED: paid campaign %s (media %s) has FAILED media — this "
            "should not be reachable given current app constraints (no media "
            "replace endpoint exists). Reason: %s. Investigate immediately.",
            campaign_id, media.id, media.transcode_error,
       )


    
@shared_task(bind=True, max_retries=3)
def _notify_campaign_submitted(self, campaign_id):
    """Email advertiser when their campaign is submitted for review."""
    try:
        campaign = Campaign.objects.select_related("advertiser__user").get(id=campaign_id)
    except Campaign.DoesNotExist:
        logger.warning("_notify_campaign_submitted: campaign %s not found", campaign_id)
        return
    try:
        sent = send_adverse_email(
            template="campaign_submitted",
            to=campaign.advertiser.user.email,
            context={
                "advertiser_name": campaign.advertiser.user.get_full_name()
                    or campaign.advertiser.user.email,
                "campaign_name": campaign.name,
                "duration_days": campaign.duration_days,
                "campaign_url": f"{_site_url()}/advertiser/campaigns/{campaign.id}/",
            },
        )
        if not sent:
            raise self.retry(exc=Exception("send_adverse_email returned False"), countdown=60)
        logger.info("Submission notification sent for campaign %s", campaign_id)
    except Exception as exc:
        logger.exception("_notify_campaign_submitted failed for campaign %s", campaign_id)
        raise self.retry(exc=exc, countdown=60)

@shared_task(bind=True, max_retries=3)
def _notify_campaign_approved(self, campaign_id):
    """Email advertiser when approved — prompts them to pick dates, not pay yet."""
    try:
        campaign = Campaign.objects.select_related("advertiser__user").prefetch_related(
            "campaign_slots__billboard"
        ).get(id=campaign_id)
    except Campaign.DoesNotExist:
        logger.warning("_notify_campaign_approved: campaign %s not found", campaign_id)
        return 
    try:
        first_slot = campaign.campaign_slots.select_related("billboard").first()
        billboard_name = first_slot.billboard.name if first_slot else "Your billboard"
        sent = send_adverse_email(
                template="campaign_approved",
                to=campaign.advertiser.user.email,
                context={
                    "advertiser_name": campaign.advertiser.user.get_full_name()
                        or campaign.advertiser.user.email,
                    "campaign_name": campaign.name,
                    "billboard_name": billboard_name,
                    "duration_days": campaign.duration_days,
                    "amount": f"{campaign.actual_price:,.2f}",
                    "select_dates_url": f"{_site_url()}/advertiser/campaigns/{campaign.id}/select-dates/",
                    "expires_in_days": 7,
                },
        )
        if not sent:
            raise self.retry(exc=Exception("send_adverse_email returned False"), countdown=60)
        logger.info("Approval notification sent for campaign %s", campaign_id)
    except Exception as exc:
        logger.exception("_notify_campaign_approved failed for campaign %s", campaign_id)
        raise self.retry(exc=exc, countdown=60)

@shared_task(bind=True, max_retries=3)
def _notify_campaign_rejected(self, campaign_id, reason):
    # Email advertiser when their campaign is rejected
    try:
        campaign = Campaign.objects.select_related(
            "advertiser__user"
        ).get(id=campaign_id)
    except Campaign.DoesNotExist:
        logger.warning("_notify_campaign_rejected: campaign %s not found", campaign_id)
        return  
    try:
        sent = send_adverse_email(
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
        if not sent:
            raise self.retry(exc=Exception("send_adverse_email returned False"), countdown=60)
        logger.info("Rejection notification sent for campaign %s", campaign_id)
    except Exception as exc:
        logger.exception("_notify_campaign_rejected failed for campaign %s", campaign_id)
        raise self.retry(exc=exc, countdown=60)
    
@shared_task(bind=True, max_retries=3)
def _notify_forwarded_to_manager(self, campaign_id):
    """Email each ad manager whose billboard is in this campaign."""
    try:
        campaign = Campaign.objects.prefetch_related(
            "campaign_slots__billboard__ad_manager__user"
        ).get(id=campaign_id)
    except Campaign.DoesNotExist:
        logger.warning("_notify_forwarded_to_manager: campaign %s not found", campaign_id)
        return
    try:
        amount = getattr(campaign, "actual_price", None) or getattr(campaign, "estimated_price", 0)
        # manager_amount = float(amount) * 0.70 if amount else 0  # matches your 70% split

        from admin_panel.models import RevenueSetting
        setting = RevenueSetting.objects.first()
        split_pct = setting.admanager_percentage if setting else Decimal("70.00")
        manager_amount = float(amount) * float(split_pct) / 100 if amount else 0

        any_sent = False
        for slot in campaign.campaign_slots.all():
            billboard = slot.billboard
            manager = billboard.ad_manager
            if not manager or not manager.user or not manager.user.email:
                continue
            sent = send_adverse_email(
                template="new_campaign_request",
                to=manager.user.email,
                context={
                    "manager_name": manager.user.get_full_name() or manager.user.email,
                    "campaign_name": campaign.name,
                    "advertiser_name": campaign.advertiser.user.get_full_name()
                        or campaign.advertiser.user.email,
                    "billboard_name": billboard.name,
                    "billboard_location": billboard.location_name,
                    "duration_days": campaign.duration_days,
                    "daily_start": campaign.daily_start_time.strftime("%H:%M"),
                    "daily_end": campaign.daily_end_time.strftime("%H:%M"),
                    "manager_amount": f"{manager_amount:,.2f}",
                    "review_url": f"{_site_url()}/admanager/campaigns/{campaign.id}/",
                },
            )
            any_sent = any_sent or sent
            if not sent:
                logger.warning(
                    "new_campaign_request email failed for manager %s, campaign %s",
                    manager.user.email, campaign_id,
                )
        if not any_sent and campaign.campaign_slots.exists():
            raise self.retry(exc=Exception("No manager notifications succeeded"), countdown=60)
        logger.info("Manager notification(s) sent for campaign %s", campaign_id)
    except Exception as exc:
        logger.exception("_notify_forwarded_to_manager failed for campaign %s", campaign_id)
        raise self.retry(exc=exc, countdown=60)

@shared_task(bind=True, max_retries=3)
def _notify_campaign_completed(self, campaign_id):
    """Email advertiser when their campaign ends."""
    try: 
        campaign = Campaign.objects.select_related(
            "advertiser__user",
            "campaign_slots__billboard",
        ).get(id=campaign_id)
    except Campaign.DoesNotExist:
        logger.warning("_notify_campaign_completed: campaign %s not found", campaign_id)
        return
    try:
        first_slot = campaign.campaign_slots.select_related("billboard").first()
        billboard_name = first_slot.billboard.name if first_slot else "Your billboard"
 
        duration_days = (campaign.end_date - campaign.start_date).days + 1
 
        sent = send_adverse_email(
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
        if not sent:
            raise self.retry(exc=Exception("send_adverse_email returned False"), countdown=60)
        logger.info("Completion notification sent for campaign %s", campaign_id)
    except Exception as exc:
        logger.exception("_notify_campaign_completed failed for campaign %s", campaign_id)
        raise self.retry(exc=exc, countdown=60)
    
# helper
def _site_url() -> str: 
    return getattr(settings, "SITE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

@shared_task(bind=True, max_retries=3)
def _notify_approval_expired(self, campaign_id):
    """Email advertiser when their approval window lapsed without picking dates."""
    try:
        campaign = Campaign.objects.select_related("advertiser__user").get(id=campaign_id)
    except Campaign.DoesNotExist:
        logger.warning("_notify_approval_expired: campaign %s not found", campaign_id)
        return
    try:
        sent = send_adverse_email(
            template="approval_expired",
            to=campaign.advertiser.user.email,
            context={
                "advertiser_name": campaign.advertiser.user.get_full_name()
                    or campaign.advertiser.user.email,
                "campaign_name": campaign.name,
                "campaign_url": f"{_site_url()}/advertiser/campaigns/{campaign.id}/",
            },
        )
        if not sent:
            raise self.retry(exc=Exception("send_adverse_email returned False"), countdown=60)
        logger.info("Approval-expired notification sent for campaign %s", campaign_id)
    except Exception as exc:
        logger.exception("_notify_approval_expired failed for campaign %s", campaign_id)
        raise self.retry(exc=exc, countdown=60)