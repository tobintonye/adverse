import hashlib
import hmac
import uuid
import logging
from decimal import Decimal
import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from .models import ( AdManagerSubaccount, AdManagerSubaccountAuditLog, CampaignPayment, PayoutRecord, compute_split, money,AdManagerEarning  )
from json import JSONDecodeError
from django.db.models import Sum
logger = logging.getLogger(__name__)
import json

# Paystack Webhook Signature Verification
def verify_paystack_signature(raw_body: bytes, signature: str) -> bool:
    if not getattr(settings, "PAYSTACK_SECRET_KEY", None):
        raise ValidationError("PAYSTACK_SECRET_KEY is not configured")
    
    key = settings.PAYSTACK_SECRET_KEY.strip()  # strip any whitespace
    expected = hmac.new(
        key.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha512,
    ).hexdigest()
    
    #print(f"DEBUG expected: {expected[:20]}")
    #print(f"DEBUG received: {signature[:20] if signature else 'NONE'}")
    
    return hmac.compare_digest(expected, signature or "")

def _paystack_headers() -> dict:
    key = getattr(settings, "PAYSTACK_SECRET_KEY", None)
    #print(f"DEBUG PAYSTACK KEY: repr='{repr(key)}'")  # add this
    if not key:
        raise ValidationError("PAYSTACK_SECRET_KEY is not configured.")
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
# testing
def _safe_json(response: requests.Response) -> dict:
    """
    Safely parse a Paystack response body. Paystack error responses (rate
    limits, gateway timeouts, WAF blocks) are sometimes empty or HTML rather
    than JSON, so response.json() can't be trusted blindly.
    """
    try:
        return response.json()
    except (JSONDecodeError, ValueError):
        logger.error(
            "Paystack returned non-JSON response (status %s): %r",
            response.status_code,
            response.text[:500],
        )
        return {}
# testing
def _paystack_request(method: str, url: str, payload: dict | None = None) -> dict:
    try:
        response = requests.request(
            method, url, json=payload, headers=_paystack_headers(), timeout=20
        )
    except requests.exceptions.Timeout:
        raise ValidationError("Paystack request timed out. Please try again.")
    except requests.exceptions.RequestException as e:
        raise ValidationError(f"Network error contacting Paystack: {e}")

    body = _safe_json(response)
    if response.status_code not in (200, 201) or not body.get("status"):
        raise ValidationError(f"Paystack API error: {body.get('message', 'Unknown error')}")
    return body


def _paystack_post(url: str, payload: dict) -> dict:
    return _paystack_request("POST", url, payload)


def _paystack_put(url: str, payload: dict) -> dict:
    return _paystack_request("PUT", url, payload)

def _paystack_get(url: str) -> dict:
    """
    Thin wrapper around requests.get for Paystack API calls.
    Raises ValidationError on network errors, timeouts, or non-200 responses.
    """
    try: 
        response = requests.get(url, headers=_paystack_headers(), timeout=20)
    except requests.exceptions.Timeout:
        raise ValidationError("Paystack request timed out. Please try again.")
    except requests.exceptions.RequestException as e:
        raise ValidationError(f"Network error contacting Paystack: {e}")
    
    body = _safe_json(response)
    if response.status_code != 200:
        raise ValidationError(
            f"Paystack API error (status {response.status_code}): "
            f"{body.get('message', 'Unknown error')}"
        )
    return body

def verify_paystack_transaction(reference: str) -> dict:
    """
    Call Paystack's verify endpoint and return the transaction data dict.
    Raises ValidationError if the transaction is not successful.
    Use this as a second check inside webhook handlers.
    """
    payload = _paystack_get( f"https://api.paystack.co/transaction/verify/{reference}" )

    data = payload.get("data") or {}
    if not payload.get("status") or data.get("status") != "success": 
        raise ValidationError("Paystack transaction is not successful.")
    return data

# Subaccount Management
def create_paystack_subaccount( ad_manager, bank_code: str, account_number: str, business_name: str ) -> AdManagerSubaccount:
    
    # resolve account name via Paystack name enquiry
    enquiry_payload = _paystack_get(
        f"https://api.paystack.co/bank/resolve"
        f"?account_number={account_number}&bank_code={bank_code}"
    )

    if not enquiry_payload.get("status"):
        raise ValidationError("Could not verify bank account details. Please check your account number and bank.")
    
    enquiry_data = enquiry_payload.get("data", {})
    resolved_account_name = enquiry_data.get("account_name", "")

    
    # creatinig subaccount on paystack percentage_charge70: ad manager gets 70%, AdVerse keeps 30%
    response_payload = _paystack_post(
        "https://api.paystack.co/subaccount",
        {
            "business_name": business_name,
            "bank_code": bank_code,
            "account_number": account_number,
            "percentage_charge": 70,
            "description": f"AdVerse subaccount for {business_name}",
        },
    )

    paystack_data = response_payload.get("data", {})
    bank_name = paystack_data.get("settlement_bank") or paystack_data.get("bank", "")

    # save locally and log.
    # Only the last 4 digits are stored — the full account number is discarded
    # after Paystack confirms the subaccount. Use subaccount_code to retrieve
    # full details from Paystack's API when needed.
    with transaction.atomic():
        subaccount = AdManagerSubaccount.objects.create(
            ad_manager=ad_manager,
            subaccount_code=paystack_data["subaccount_code"],
            business_name=business_name,
            bank_name=bank_name,
            bank_code=bank_code,
            account_number_last4=account_number[-4:],
            account_name=resolved_account_name,
            settlement_bank=paystack_data.get("settlement_bank", ""),
            gateway_response=_safe_gateway_response(paystack_data),
            verified_at=None,  # mark_verified() called separately after confirmation
        )
        AdManagerSubaccountAuditLog.objects.create(
            subaccount=subaccount,
            event=AdManagerSubaccountAuditLog.Event.CREATED,
            note=f"Paystack subaccount created for subaccount id={subaccount.id}.",
        )
    return subaccount


def update_paystack_subaccount_bank_details( subaccount: AdManagerSubaccount, bank_code: str,  account_number: str, 
                                             business_name: str | None,  updated_by ) -> AdManagerSubaccount:
    enquiry_payload = _paystack_get(
        f"https://api.paystack.co/bank/resolve"
        f"?account_number={account_number}&bank_code={bank_code}"
    )

    if not enquiry_payload.get("status"):
        raise ValidationError("Could not verify new bank account details." "Please check your account number and bank.")
    enquiry_data = enquiry_payload.get("data", {})
    resolved_account_name = enquiry_data.get("account_name", "")

    # update subaccount on Paystack
    update_payload: dict = {
        "bank_code": bank_code, 
        "account_number": account_number
    }

    if business_name:
        update_payload["business_name"] = business_name

    response_payload = _paystack_put(
    f"https://api.paystack.co/subaccount/{subaccount.subaccount_code}",
    update_payload,
)
    paystack_data = response_payload.get("data", {})
    new_bank_name = (
        paystack_data.get("settlement_bank")
        or paystack_data.get("bank", "")
        or subaccount.bank_name
    )

    # update locally (last 4 digits only, never full number)
    subaccount.update_bank_details(
        bank_name=new_bank_name,
        bank_code=bank_code,
        account_number_last4=account_number[-4:],
        account_name=resolved_account_name,
        updated_by=updated_by,
    )
    return subaccount

# Campaign Payment Initialization
def initialize_campaign_payment(campaign) -> dict:
    """
        Initialize a Paystack transaction for a campaign payment with automatic split.
    
        Before calling this:
        - Campaign must be approved and ready for payment
        - Ad manager must have an active, verified subaccount
    
        Returns the Paystack initialization response data containing:
        - authorization_url: redirect the advertiser here
        - access_code: for Paystack inline popup
        - reference: AdVerse's reference (also stored on CampaignPayment)
    
        Safety: The local CampaignPayment record is created BEFORE calling Paystack.
        If the Paystack call fails, the local record is deleted so we never have an
        active Paystack checkout without a matching local record.
    """

    existing_payment = getattr(campaign, "payment", None)
    if existing_payment is not None:
        if existing_payment.status == CampaignPayment.Status.COMPLETED:
            raise ValidationError("This campaign has already been paid for.")
        if existing_payment.status == CampaignPayment.Status.PENDING:
            raise ValidationError(
                "A payment is already in progress for this campaign. "
                "Please complete or wait for it to expire before retrying."
            )
        raise ValidationError(
            "A previous payment attempt for this campaign did not succeed. "
            "Please contact support to retry."
        )

    # Never take money for content that isn't verified safe to play. Human approval (full_approved) is about content/policy; this is a separate automated check
    # that the file can actually be decoded on the billboard hardware. Both must pass before payment is even offered/
    media = campaign.media
    if not media.is_playable:
        if media.transcode_status == media.TranscodeStatus.FAILED:
            raise ValidationError(
                "This campaign's media failed processing and cannot be played on billboard hardware. "
                "Please replace the file before paying for this campaign. "
                f"(Reason: {media.transcode_error or 'unknown'})"
            )
        raise ValidationError(
            "This campaign's media is still being processed. Please try again in a few minutes."
        )
    first_slot = (
        campaign.campaign_slots
        .select_related("billboard__ad_manager__paystack_subaccount")
        .first()
    )
    if not first_slot:
        raise ValidationError(
            "This campaign has no billboard slots assigned. "
            "Please add a billboard before paying."
        )
    billboard = first_slot.billboard
    ad_manager = billboard.ad_manager
    subaccount = ad_manager.paystack_subaccount
    subaccount.assert_ready_for_payment()
    
    total_amount = money(campaign.actual_price)
    platform_fee, manager_amount = compute_split(total_amount)
    reference = f"adv-{uuid.uuid4().hex}"
    amount_kobo = int(total_amount * 100)

    # create local record BEFORE calling Paystack.
    # This ensures that if Paystack succeeds but the DB write fails,
    # we don't end up with money taken and no local record.

    payment = CampaignPayment.objects.create( 
        campaign=campaign,
        subaccount=subaccount,
        total_amount=total_amount,
        platform_fee=platform_fee,
        manager_amount=manager_amount,
        reference=reference,
        status=CampaignPayment.Status.PENDING,
    )
    # call Paystack. If this fails, clean up the local record.
    try: 
         response_payload = _paystack_post(
            "https://api.paystack.co/transaction/initialize",
            {
                "email": campaign.advertiser.user.email,
                "amount": amount_kobo,
                "reference": reference,
                "subaccount": subaccount.subaccount_code,
                # bearer='account': AdVerse bears Paystack's fee,
                # ad manager receives full 70% undeducted.
                "bearer": "account",
                "metadata": {
                    "campaign_id": str(campaign.id),
                    "campaign_name": campaign.name,
                    "ad_manager_id": str(ad_manager.id),
                    "platform_fee": str(platform_fee),
                    "manager_amount": str(manager_amount),
                },
            },
        )
    except ValidationError:
        payment.delete()
        raise
 
    return response_payload.get("data", {})

# Webhook Handler — charge.success
def handle_charge_success(event_data: dict) -> CampaignPayment | None:
    """
    Called from the Paystack webhook view when event == 'charge.success'.
 
    Verifies the payment against Paystack's API (second check beyond
    signature verification), confirms the amount matches, then marks the
    CampaignPayment as completed — which also creates the AdManagerEarning
    log record.
 
    Always idempotent — safe to call multiple times for the same reference.
    """
    reference = event_data.get("data", {}).get("reference", "")
    if not reference:
        raise ValidationError("Webhook payload missing reference.")
 
    # Only process payments we initialized (our references start with 'adv-')
    if not reference.startswith("adv-"):
        return None
 
    try:
        payment = CampaignPayment.objects.get(reference=reference)
    except CampaignPayment.DoesNotExist:
        raise ValidationError(f"No CampaignPayment found for reference: {reference}")

    if payment.status == CampaignPayment.Status.COMPLETED:
        return payment

    # Late webhook arriving after expire_stale_campaign_payments marked this FAILED.
    # Money was collected — flag for immediate manual review and potential refund.
    if payment.status == CampaignPayment.Status.FAILED:
        logger.error(
            "Late charge.success webhook for already-expired payment %s "
            "(reference=%s). Manual refund review required.",
            payment.id,
            reference,
        )
        raise ValidationError(
            f"Payment {payment.id} was already marked FAILED (expired). "
            "A refund may be required — manual review needed."
        )
    
    # Second verification call Paystack directly to confirm
    paystack_data = verify_paystack_transaction(reference)

    # Extract Paystack's own transaction reference (string) and numeric ID separately
    paystack_transaction_id = str(paystack_data.get("id", ""))
    paystack_reference = paystack_data.get("reference", "") or paystack_transaction_id

    # Guard against amount mismatch prevents undercharge attacks
    verified_amount_kobo = paystack_data.get("amount", 0)
    verified_amount = money(Decimal(str(verified_amount_kobo)) / 100)
 
    if verified_amount != payment.total_amount:
        logger.error(
            "Amount mismatch on payment %s: expected NGN %s, Paystack confirmed NGN %s. "
            "Manual review required.",
            payment.id,
            payment.total_amount,
            verified_amount,
        )
        raise ValidationError(
            f"Payment amount mismatch for payment {payment.id}. Manual review required."
        )
 
    payment.mark_completed(
        paystack_reference=paystack_reference,
        gateway_response=_safe_gateway_response(paystack_data),
        verified_amount=verified_amount,
    )
    return payment


# Refund
def initiate_campaign_refund(campaign, initiated_by=None) -> dict:
    """
    Initiates a refund for a completed campaign payment via Paystack's API.
 
    The actual mark_refunded() on the CampaignPayment model is called from
    the Paystack refund webhook NOT here. This function only triggers the
    refund on Paystack's side.
 
    Re-verifies the transaction state with Paystack before initiating to
    avoid double-refund attempts or refunding an already-charged-back payment.
 
    Raises ValidationError if the campaign payment is not in a refundable state.
    """
    payment = campaign.payment
    if payment.status != CampaignPayment.Status.COMPLETED:
        raise ValidationError("Only completed payments can be refunded.")
 
    # Re-verify with Paystack before initiating confirms the transaction is
    # still in a refundable state (not already charged back or partially refunded)
    paystack_data = verify_paystack_transaction(payment.reference)
    if paystack_data.get("status") != "success":
        raise ValidationError(
            "Paystack transaction is not in a refundable state. Manual review required."
        )
 
    amount_kobo = int(money(payment.total_amount) * 100)
 
    response_payload = _paystack_post(
        "https://api.paystack.co/refund",
        {
            "transaction": payment.paystack_reference,
            "amount": amount_kobo,
        },
    )
    return response_payload.get("data", {})

def _safe_gateway_response(data: dict) -> dict:
    """
    Strip PII fields from a Paystack response dict before storing in the DB.
    Paystack responses can include customer email, card BIN, IP address, and
    other sensitive data that should not be persisted unnecessarily.
    """
    PII_KEYS = {
        "customer",
        "ip_address",
        "authorization",
        "requested_amount",
        "paidAt",
        "createdAt",
        "transaction_date",
        "log",
    }
    return {k: v for k, v in data.items() if k not in PII_KEYS}


