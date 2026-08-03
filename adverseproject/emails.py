import logging
from datetime import date
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
import re
logger = logging.getLogger(__name__)

# Central email utility for AdVerse. All emails go through send_adverse_email() — one function, consistent formatting.

# Map template name → (subject, html_template_path)
EMAIL_TEMPLATES = {
    "campaign_submitted": (
        "Campaign submitted for review",
        "emails/campaign_submitted.html",
    ),
    "campaign_approved": (
        "Campaign approved — payment required",
        "emails/campaign_approved.html",
    ),
     "campaign_rejected": (
        "Your campaign was not approved",
        "emails/campaign_rejected.html",
    ),
    "campaign_completed": (
        "Your campaign has ended",
        "emails/campaign_completed.html",
    ),
    "payment_confirmed": (
        "Payment confirmed — your campaign is live",
        "emails/payment_confirmed.html",
    ),
    "new_campaign_request": (
        "New campaign request for your billboard",
        "emails/new_campaign_request.html",
    ),
    "earnings_credited": (
        "Earnings credited to your balance",
        "emails/earnings_credited.html",
    ),
    "payout_processed": (
        "Payout sent to your bank",
        "emails/payout_processed.html",
    ),
    # auth emails
    "verify_email": (
        "Verify your Advers account",
        "emails/verify_email.html",
    ),
    "password_reset": (
        "Reset your Advers password",
        "emails/password_reset.html",
    ),
    "password_changed": (
        "Your Advers password was changed",
        "emails/password_changed.html",
    ),
    "staff_reconciliation": (
    "Daily Reconciliation",
    "emails/staff_reconciliation.html",
    ),
    "staff_flagged_payouts": (
        "Suspicious Payout(s) Flagged",
        "emails/staff_flagged_payouts.html",
    ),
    "contact_message": (
        "New contact message received",
        "emails/contact_message.html",
    ),
}

def send_adverse_email(template: str, to: str | list[str], context: dict, subject_prefix: str = "[AdVers]",) -> bool:
    """
    Render and send an AdVers email.
 
    Args:
        template: Key from EMAIL_TEMPLATES (e.g. "campaign_approved")
        to: Recipient email address or list of addresses
        context: Template context variables
        subject_prefix: Prepended to the subject line
 
    Returns:
        True if sent successfully, False otherwise.
        Never raises — failures are logged and swallowed so a broken
        email never rolls back a payment or approval transaction.
    """
    if template not in EMAIL_TEMPLATES: 
        logger.error("send_adverse_email: unknown template '%s'", template)
        return False
    
    subject_base, html_template = EMAIL_TEMPLATES[template]
    subject = f"{subject_prefix} {subject_base}"

    # Always inject year for footer copyright
    context.setdefault("year", date.today().year)
    context.setdefault("site_name", "AdVers")
    try:
        html_content = render_to_string(html_template, context)
        # Plain text fallback — strip tags crudely but reliably
        text_content = re.sub(r"<[^>]+>", "", html_content)
        text_content = re.sub(r"\n\s*\n\s*\n", "\n\n", text_content).strip()
 
        recipients = [to] if isinstance(to, str) else to
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients,
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send()
        logger.info("Email sent: template=%s to=%s subject=%s",template, recipients, subject,)
        return True
 
    except Exception as e:
        logger.error("Email failed: template=%s to=%s error=%s",template, to, e,)
        return False