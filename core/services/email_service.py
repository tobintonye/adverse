import logging
import time
import random
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.urls import reverse
from django_q.tasks import async_task

logger = logging.getLogger(__name__)


def send_verification_email(user, request):
    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    verification_url = request.build_absolute_uri(
        reverse("security:verifyemail", kwargs={"uidb64": uid, "token": token})
    )
    async_task(
        "core.tasks.task_send_verification_email",
        user.pk,
        verification_url,
    )
    logger.info("Verification email queued for user %s", user.pk)


def send_password_reset_email(user, request):
    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    reset_url = request.build_absolute_uri(
        reverse("security:newpasswordReset", kwargs={"uidb64": uid, "token": token})
    )
    async_task(
        "core.tasks.task_send_password_reset_email",
        user.pk,
        reset_url,
    )
    logger.info("Password reset email queued for user %s", user.pk)


def send_password_reset_email_safe(user, request):
    """Timing-safe wrapper — call this from all public endpoints."""
    if user is None:
        time.sleep(random.uniform(0.8, 1.5))
        return
    send_password_reset_email(user, request)

def send_password_changed_email(user): 
    async_task(
        "ore.tasks.task_send_password_changed_email",
        user.pk
    )
    logger.info("Password-changed notification queued for user %s", user.pk)