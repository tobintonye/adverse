import logging
from django.contrib.auth import get_user_model
from django.core.mail import send_mail, BadHeaderError
from django.conf import settings
import smtplib
import socket
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)
User = get_user_model()


def _send_email(subject, message, recipient_email):
    """Private — only called by tasks below. Raises so Q2 can retry."""
    try:
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [recipient_email])
    except (BadHeaderError, smtplib.SMTPException, socket.error, ImproperlyConfigured) as e:
        logger.error("Email send failed to %s: %s", recipient_email, e)
        raise


def task_send_verification_email(user_pk, verification_url):
    try:
        user = User.objects.get(pk=user_pk)
    except User.DoesNotExist:
        logger.warning("task_send_verification_email: user %s not found", user_pk)
        return  # user deleted between enqueue and execution — don't retry

    subject = "Verify your Adverse account"
    message = f"""Hi {user.first_name},

Thanks for creating an account with Adverse!

Please verify your email by clicking the link below:
{verification_url}

If you didn't create an account, you can safely ignore this email.

Best regards,
The Adverse Team
"""
    _send_email(subject, message, user.email)
    logger.info("Verification email sent to %s", user.email)


def task_send_password_reset_email(user_pk, reset_url):
    try:
        user = User.objects.get(pk=user_pk)
    except User.DoesNotExist:
        logger.warning("task_send_password_reset_email: user %s not found", user_pk)
        return

    subject = "Password Reset – Adverse"
    message = f"""Hello {user.first_name},

You requested a password reset. Click the link below:
{reset_url}

If you didn't request this, ignore this email.

This link expires in 24 hours.

Best regards,
The Adverse Team
"""
    _send_email(subject, message, user.email)
    logger.info("Password reset email sent to %s", user.email)