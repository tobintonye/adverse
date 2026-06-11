from django.dispatch import receiver
from django.contrib.auth.signals import user_login_failed
import logging

logger = logging.getLogger(__name__)

@receiver(user_login_failed)
def log_failed_login(sender, credentials, request, **kwargs):
    ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', 'unknown'))
    logger.warning(
        "Failed login attempt",
        extra={
            "email": credentials.get("email"),
            "ip": ip,
        }
    )