import logging
from datetime import timedelta
 
from celery import shared_task
from django.core.cache import cache
from django.core.mail import send_mail
from django.conf import settings
from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone

from .models import ( AdManagerEarning, AdManagerSubaccount, AdManagerSubaccountAuditLog, CampaignPayment, PayoutRecord)
logger = logging.getLogger(__name__)

"""
Celery tasks for the payments module.

These tasks run in the background and handle:
- Fraud detection on payout records
- Stale payment cleanup
- Reconciliation alerts
"""

# Fraud Detection
@shared_task(bind=True, max_retries=3)
def flag_suspicious_payouts(self):
    """
    Runs every 6 hours. Checks recent payout records for suspicious patterns
    and flags them for internal review.
 
    Triggers:
    - Large payout shortly after bank details were changed
    - Payout amount exceeds total recent earnings (last 30 days)
    - More than 3 payouts in 24 hours from the same ad manager
 
    Safety guarantees:
    - Idempotency lock prevents overlapping runs via Django cache.
    - All flag writes are wrapped in a single atomic transaction so a
      mid-run crash never leaves a partially-flagged batch.
    - subaccount_code is never written to logs (use internal UUID instead).
    - Earnings lookup is pre-aggregated to avoid N+1 queries.
    """
    # Idempotency lock (30-minute window) 
    LOCK_KEY = "lock:flag_suspicious_payouts"
    if not cache.add(LOCK_KEY, "1", timeout=60 * 30):
        logger.info("flag_suspicious_payouts already running — skipping duplicate run.")
        return
    try: 
        now = timezone.now()
        flagged_count = 0
        payout_ids_to_flag = []  # collect (payout, reason) pairs before writing

        # Trigger 1 — payout within 48 hours of a bank detail change
        recent_payouts = (PayoutRecord.objects.filter(status=PayoutRecord.Status.PENDING, is_flagged=False, created_at__gte=now - timedelta(hours=48)).select_related("subaccount", "ad_manager"))

        for payout in recent_payouts:
            subaccount = payout.subaccount
            recent_bank_change = subaccount.audit_logs.filter(
                event=AdManagerSubaccountAuditLog.Event.BANK_DETAILS_CHANGED, 
                created_at__gte=now - timedelta(hours=48),
            ).exists()

            if recent_bank_change:
                payout_ids_to_flag.append((
                    payout,
                    (
                        f"Payout of NGN {payout.amount} initiated within 48 hours "
                        f"of bank detail change (subaccount id={subaccount.id})."
                    ),
                ))

        # Trigger 2 — payout exceeds total earnings in the last 30 days
        earnings_by_manager = dict(AdManagerEarning.objects.filter(earned_at__gte=now - timedelta(days=30)).values("ad_manager").annotate(total=Sum("amount")).values_list("ad_manager", "total"))

        unflagged_payouts = (PayoutRecord.objects.filter(status=PayoutRecord.Status.PENDING, is_flagged=False).select_related("ad_manager"))

        for payout in unflagged_payouts:
            # Skip if already queued for flagging from Trigger 1
            if any(p.id == payout.id for p, _ in payout_ids_to_flag): 
                continue

            total_earnings = earnings_by_manager.get(payout.ad_manager_id, 0)
            if payout.amount > total_earnings:
                payout_ids_to_flag.append((payout, (f"Payout of NGN {payout.amount} exceeds total earnings ", f"of NGN {total_earnings} in the last 30 days."),))

        # Trigger 3 — more than 3 UNFLAGGED payouts in 24 hours
        # is_flagged=False applied to both the count and the fetch so the
        # reason string reflects the true unflagged frequency.
        high_frequency = (PayoutRecord.objects.filter(created_at__gte=now - timedelta(hours=24), is_flagged=False).values("ad_manager").annotate(count=Count("id")).filter(count__gte=3))

        already_queued_ids = {p.id for p, _ in payout_ids_to_flag}

        for entry in high_frequency:
            recent = PayoutRecord.objects.filter(
                ad_manager_id = entry["ad_manager"], 
                created_at__gte = now - timedelta(hours=24), 
                is_flagged=False,
            )
            for payout in recent: 
                if payout.id in already_queued_ids:
                    continue
                payout_ids_to_flag.append((payout, (f"High frequency: {entry['count']} unflagged payouts in the last 24 hours",  f"from the same ad manager."),))
                already_queued_ids.add(payout.id)

        with transaction.atomic(): 
            for payout, reason in payout_ids_to_flag:
                payout.flag(reason=reason)
                flagged_count += 1
                logger.warning(
                    "Flagged payout id=%s for ad_manager id=%s — %s",
                    payout.id,
                    payout.ad_manager_id,
                    reason,
                ) 
        logger.info("flag_suspicious_payouts completed — %d record(s) flagged.", flagged_count)
        
        if flagged_count > 0:
            _alert_staff_flagged_payouts(flagged_count)
    except Exception as exc: 
        logger.exception("flag_suspicious_payouts failed: %s", exc)
        raise self.retry(exc=exc, countdown=60 * 5)
    finally:
        cache.delete(LOCK_KEY)

# Stale Payment Cleanup
@shared_task(bind=True, max_retries=3)
def expire_stale_campaign_payments(self):
    """
    Runs daily at midnight. Marks campaign payments that have been PENDING
    for more than 24 hours as FAILED. These are payments where the advertiser
    opened the Paystack checkout but never completed it.
 
    NOTE — webhook race condition:
    A payment may still be PENDING because Paystack's webhook hasn't arrived
    yet (network delay). Our webhook handler MUST guard against a late
    webhook arriving after this task has already marked a payment FAILED:
 
        if payment.status == CampaignPayment.Status.FAILED:
            logger.warning("Late webhook for expired payment %s", payment.id)
            # decide: trigger a refund, alert staff, or ignore
            return
 
    We iterate and call save() individually so that any post_save signals,
    audit log entries, or status-change hooks defined on CampaignPayment
    are fired correctly. Use .iterator() to avoid loading all rows into
    memory at once.
    """
    try: 
        cutoff = timezone.now() - timedelta(hours=24)
        stale =  CampaignPayment.objects.filter(
            status=CampaignPayment.Status.PENDING,
            created_at__lt=cutoff,
        )
        count = 0
        for payment in stale.iterator():
            payment.status = CampaignPayment.Status.FAILED
            payment.save(update_fields=["status"])
            count += 1
        logger.info("expire_stale_campaign_payments — %d stale payment(s) marked FAILED.", count)
    except Exception as exc:
        logger.exception("expire_stale_campaign_payments failed: %s", exc)
        raise self.retry(exc=exc, countdown=60 * 10)

# Daily Reconciliation Alert
@shared_task(bind=True, max_retries=3)
def send_reconciliation_alert(self):
    """
    Runs daily at 8am. Sends a summary email to AdVerse staff with:
    - Total completed payments yesterday
    - Total platform fees collected yesterday
    - Total ad manager earnings yesterday
    - Count of flagged payouts pending review
    """
    try: 
        yesterday_start = (timezone.now() - timedelta(day=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) 
        yesterday_end = yesterday_start + timedelta(days=1)

        completed = CampaignPayment.objects.filter(
            status=CampaignPayment.Status.COMPLETED,
            completed_at__range=(yesterday_start, yesterday_end),
        )

        total_revenue = completed.aggregate(total=Sum("total_amount"))["total"] or 0
        total_fees = completed.aggregate(total=Sum("platform_fee"))["total"] or 0
        total_manager_earnings = completed.aggregate(total=Sum("manager_amount"))["total"] or 0
        flagged_payouts =  PayoutRecord.objects.filter(is_flagged=True, status=PayoutRecord.Status.PENDING).count()

        message = (
            f"AdVerse Daily Reconciliation — {yesterday_start.date()}\n\n"
            f"Completed Payments: {completed.count()}\n"
            f"Total Revenue:      NGN {total_revenue:,.2f}\n"
            f"Platform Fees:      NGN {total_fees:,.2f}\n"
            f"Manager Earnings:   NGN {total_manager_earnings:,.2f}\n\n"
            f"Flagged Payouts Pending Review: {flagged_payouts}\n"
        )
        if flagged_payouts > 0:
            message += "\nACTION REQUIRED: Review flagged payouts in the admin dashboard.\n"
    
        send_mail(
            subject=f"[AdVerse] Daily Reconciliation — {yesterday_start.date()}",
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=getattr(
                settings, "BILLING_ALERT_EMAILS", [settings.DEFAULT_FROM_EMAIL]
            ),
            fail_silently=False,
        )
        logger.info("send_reconciliation_alert email sent.")
    except Exception as exc:
        logger.exception("send_reconciliation_alert failed: %s", exc)
        raise self.retry(exc=exc, countdown=60 * 5)

# Internal Helpers
def _alert_staff_flagged_payouts(count: int) -> None:
    # Send an immediate email alert when payouts are flagged.
    try:
        admin_base_url = getattr(settings, "ADMIN_BASE_URL", "")
        send_mail(
            subject=f"[AdVerse] {count} Suspicious Payout(s) Flagged",
            message=(
                f"{count} payout record(s) have been flagged as suspicious and require review.\n\n"
                f"Please check the admin dashboard:\n"
                f"{admin_base_url}/admin/billing/payoutrecord/?is_flagged__exact=1"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=getattr(
                settings, "BILLING_ALERT_EMAILS", [settings.DEFAULT_FROM_EMAIL]
            ),
            fail_silently=True,
        )
    except Exception as e:
        logger.error("Failed to send flagged payout alert email: %s", e)

@shared_task
def sync_all_subaccounts():
    """
    Daily task — checks all active subaccounts against Paystack
    and deactivates any that no longer exist.
    """
    from payments.models import AdManagerSubaccount
    active = AdManagerSubaccount.objects.filter(is_active=True)
    for sub in active:
        sub.sync_with_paystack()
    logger.info("sync_all_subaccounts completed for %d subaccounts.", active.count())