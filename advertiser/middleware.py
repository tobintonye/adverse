"""
import logging
from advertiser.models import Campaign

logger = logging.getLogger(__name__)

class CampaignStatusSyncMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            try:
                Campaign.update_statuses()
            except Exception as e:
                logger.error(f"Failed to dynamically update campaign statuses: {e}")
                
        response = self.get_response(request)
        return response
"""