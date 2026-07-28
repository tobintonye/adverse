import logging
from django.contrib.auth import get_user_model
from django.core.mail import send_mail, BadHeaderError
from django.conf import settings
import smtplib
import socket
from django.core.exceptions import ImproperlyConfigured
from adverseproject.emails import send_adverse_email
from celery import shared_task

logger = logging.getLogger(__name__)
User = get_user_model()

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def task_send_verification_email(self, user_pk, verification_url):
    try:
        user = User.objects.get(pk=user_pk)
    except User.DoesNotExist:
        logger.warning("task_send_verification_email: user %s not found", user_pk)
        return  # user deleted between enqueue and execution don't retry

    sent = send_adverse_email(
        template="verify_email",
        to=user.email,
        context={
            "first_name": user.first_name or user.email,
            "verification_url": verification_url,
        },
    )
    if not sent:
        raise self.retry(exc=Exception("send_adverse_email returned False"))
 
    logger.info("Verification email sent to %s", user.email)

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def task_send_password_reset_email(self, user_pk, reset_url):
    try:
        user = User.objects.get(pk=user_pk)
    except User.DoesNotExist:
        logger.warning("task_send_password_reset_email: user %s not found", user_pk)
        return

    sent = send_adverse_email(
        template="password_reset",
        to=user.email,
        context={
            "first_name": user.first_name or user.email,
            "reset_url": reset_url,
        },
    )
    if not sent:
        raise self.retry(exc=Exception("send_adverse_email returned False"))
 
    logger.info("Password reset email sent to %s", user.email)

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def task_send_password_changed_email(self, user_pk):
    try:
        user = User.objects.get(pk=user_pk)
    except User.DoesNotExist:
        logger.warning("task_send_password_changed_email: user %s not found", user_pk)
        return
 
    sent = send_adverse_email(
        template="password_changed",
        to=user.email,
        context={
            "first_name": user.first_name or user.email,
        },
    )
    if not sent:
        raise self.retry(exc=Exception("send_adverse_email returned False"))
 
    logger.info("Password-changed notification sent to %s", user.email)