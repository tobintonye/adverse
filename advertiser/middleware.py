import logging

from django.core.cache import cache
from django.utils import timezone

from advertiser.models import Campaign

logger = logging.getLogger("advertiser.middleware")


class CampaignStatusSyncMiddleware:
   

    SYNC_INTERVAL = 60 * 5  # run at most once every 5 minutes
    LOCK_KEY = "campaign_status_sync:last_run"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        self._maybe_sync()
        return self.get_response(request)

    def _maybe_sync(self):
        # cache.add only succeeds if the key isn't already set — this is
        # both our throttle and our cross-process lock in one operation.
        if not cache.add(self.LOCK_KEY, "1", timeout=self.SYNC_INTERVAL):
            return

        try:
            today = timezone.now().date()

            activated = Campaign.objects.filter(
                status=Campaign.Status.APPROVED,
                start_date__lte=today,
            ).update(status=Campaign.Status.ACTIVE)

            completed = Campaign.objects.filter(
                status=Campaign.Status.ACTIVE,
                end_date__lt=today,
            ).update(status=Campaign.Status.COMPLETED)

            if activated or completed:
                logger.info(
                    "CampaignStatusSyncMiddleware: activated=%d completed=%d (as of %s)",
                    activated, completed, today,
                )
        except Exception:
            # Never let a sync failure break the request. The cache lock
            # already prevents this from being retried in a tight loop;
            # next request after SYNC_INTERVAL will just try again.
            logger.exception("CampaignStatusSyncMiddleware: sync failed")