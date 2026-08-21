import logging

from django.core.cache import cache
from django.utils import timezone
from scheduling.tasks import activate_due_campaigns, expire_old_campaigns
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
            activate_due_campaigns()
            expire_old_campaigns()
        except Exception:
            logger.exception("CampaignStatusSyncMiddleware: sync failed")