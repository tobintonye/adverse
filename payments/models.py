from django.db import models
import uuid
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from common.models import TimeStampedModel
from django.db.models import CheckConstraint, Q

User = get_user_model() 

NAIRA = Decimal("0.01")
PLATFORM_FEE_PERCENT = Decimal("10.00")

def money(value):
    #  Normalize and validate a monetary amount
    amount = Decimal(str(value)).quantize(NAIRA, ROUND_HALF_UP)
    if amount <= 0:
        raise ValidationError("Amount must be positive.")
    return amount

def compute_split(total_amount):
    """
    Returns (platform_fee, ad_manager_amount) for a given total.
    Always uses PLATFORM_FEE_PERCENT so the split is consistent everywhere.
    """
    total = money(total_amount)
    fee = (total * PLATFORM_FEE_PERCENT / Decimal("100")).quantize(NAIRA, rounding=ROUND_HALF_UP)
    manager_amount = total - fee
    return fee, manager_amount

# Returns last 4 digits masked: ******1234
def mask_account_number(account_number : str) -> str: 
    if not account_number:
        return ""
    return f"*****{account_number[-4:]}"

class AdManagerSubaccount(TimeStampedModel):
    # One Paystack subaccount per ad manager.
    ad_manager = models.OneToOneField("admanager.Admanager", on_delete=models.PROTECT, related_name="paystack_subaccount")
    subaccount_code = models.CharField(max_length=120, unique=True)
    bank_name = models.CharField(max_length=120)
    bank_code = models.CharField(max_length=10)
    account_number = models.CharField(max_length=20)
    account_name = models.CharField(max_length=180)
    settlement_bank = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    gateway_response = models.JSONField(default=dict, blank=True) # raw Paystack subaccount response

    @property
    def mask_account_number(self): 
        return mask_account_number(self.account_number)

    @property
    def is_verified(self):
        return self.verified_at is not None
    
    def deactivate(self, reason="", changed_by=None): 
        """
        Suspend this subaccount. No new campaign payments will route to it.
        Existing campaigns are unaffected. Audit trail preserved.
        """
        with transaction.atomic():
            self.is_active = False
            self.save(update_fields=["is_active", "updated_at"])
            AdManagerSubaccountAuditLog.objects.create(
                subaccount=self,
                event=AdManagerSubaccountAuditLog.Event.DEACTIVATED,
                changed_by=changed_by,
                note=reason,
            )

    def reactivate(self, changed_by=None):
        with transaction.atomic():
            self.is_active = True
            self.save(update_fields=["is_active", "updated_at"])
            AdManagerSubaccountAuditLog.objects.create(
                subaccount=self,
                event=AdManagerSubaccountAuditLog.Event.REACTIVATED,
                changed_by=changed_by,
            )

    def update_bank_details(self, bank_name, bank_code, account_number, account_name, updated_by):
        """
        Update bank details and log the change with masked old values.
        Clears verified_at — subaccount must be re-verified before accepting payments.
        Caller must also update the subaccount on Paystack via their API.
        """
        # Log masked old details — never store plain account numbers in audit notes
        masked_old = {
            "bank_name": self.bank_name,
            "bank_code": self.bank_code,
            "account_number": mask_account_number(self.account_number), 
            "account_name":self.account_name,
        }
        with transaction.atomic():
            self.bank_name = bank_name
            self.bank_code = bank_code
            self.account_number = account_number
            self.account_name = account_name
            self.verified_at = None  # must re-verify after bank change
            self.save(update_fields=[
                "bank_name", "bank_code", "account_number",
                "account_name", "verified_at", "updated_at",
            ])
            AdManagerSubaccountAuditLog.objects.create(
                subaccount=self,
                event=AdManagerSubaccountAuditLog.Event.BANK_DETAILS_CHANGED,
                changed_by=updated_by,
                note=f"Previous details: {masked_old}",
            )
    def mark_verified(self, changed_by=None):
        # Call after confirming bank details with Paystack name enquiry.
        with transaction.atomic():
            self.verified_at = timezone.now()
            self.save(update_fields=["verified_at", "updated_at"])
            AdManagerSubaccountAuditLog.objects.create(
                subaccount=self,
                event=AdManagerSubaccountAuditLog.Event.VERIFIED,
                changed_by=changed_by,
            )

    def assert_ready_for_payment(self):
        """
        Call this before initializing a Paystack transaction for a campaign
        that routes to this subaccount. Raises if the subaccount cannot
        safely receive payments.
        """
        if not self.is_active:
            raise ValidationError(
                "This ad manager's payment account is currently inactive. "
                "Please contact support."
            )
        if not self.is_verified:
            raise ValidationError(
                "This ad manager's bank details have not been verified yet. "
                "Payment cannot proceed."
            )

    def __str__(self):
        return f"Subaccount [{self.ad_manager}] {self.subaccount_code}"

    class Meta:
        indexes = [
            models.Index(fields=["is_active"]),
            models.Index(fields=["subaccount_code"]),
        ]
class AdManagerSubaccountAuditLog(TimeStampedModel):
    """
    Immutable log of every sensitive change to an ad manager's subaccount.
    Used for fraud investigation and compliance.
    Never updated or deleted.
    """
    class Event(models.TextChoices):
        CREATED = "created", "Created"
        BANK_DETAILS_CHANGED = "bank_details_changed", "Bank Details Changed"
        DEACTIVATED = "deactivated", "Deactivated"
        REACTIVATED = "reactivated", "Reactivated"
        VERIFIED = "verified", "Verified"

    subaccount = models.ForeignKey(AdManagerSubaccount, on_delete=models.PROTECT, related_name="aduit_logs")
    event = models.CharField(max_length=32, choices=Event.choices)
    changed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL,related_name="subaccount_audit_logs",)
    note = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        # Immutable — block any update attempt, not just ones where pk is set in memory
        if self.pk and AdManagerSubaccountAuditLog.objects.filter(pk=self.pk).exists():
            raise ValidationError("Subaccount audit logs are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Subaccount audit logs cannot be deleted.")
    
    def __str__(self):
        return f"AuditLog [{self.subaccount.ad_manager}] {self.event} @ {self.created_at}"
    
    class Meta:
        indexes = [
            models.Index(fields=["subaccount", "created_at"]),
            models.Index(fields=["event"]),
        ]


class CampaignPayment(TimeStampedModel):
    """
    Records the outcome of an advertiser paying for a campaign via Paystack.

    Flow (Paystack handles the split):
    1. AdVerse initializes a Paystack transaction with the ad manager's
       subaccount_code. Paystack splits automatically:
         - platform_fee (10%) → AdVerse main Paystack account
         - manager_amount (90%) → Ad manager's Paystack subaccount
    2. Paystack fires a webhook confirming payment.
    3. AdVerse verifies the webhook, then calls mark_completed().
    4. An AdManagerEarning log record is created for the ad manager's dashboard.

    AdVerse never holds the money. Paystack does the split.

    FRAUD CONTROLS:
    - Before initializing the Paystack transaction, call
      subaccount.assert_ready_for_payment() to ensure the subaccount
      is active and verified.
    - verified_amount is checked against total_amount in mark_completed()
      to catch any amount tampering.
    - paystack_reference ties this record to an auditable Paystack transaction.
    - split integrity is enforced: platform_fee + manager_amount == total_amount.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    campaign = models.OneToOneField("advertiser.Campaign", on_delete=models.PROTECT, related_name="payment")
    subaccount = models.ForeignKey(AdManagerSubaccount, on_delete=models.PROTECT, related_name="campaign_payments",)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    platform_fee = models.DecimalField(max_digits=12, decimal_places=2)
    manager_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    reference = models.CharField(max_length=120, unique=True) # AdVerse-generated
    paystack_reference = models.CharField(max_length=120, blank=True)  # Paystack's reference
    gateway_response = models.JSONField(default=dict, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    refund_reference = models.CharField(max_length=120, blank=True)

    def clean(self):
        # Enforce split integrity at the model level.
        if self.total_amount and self.platform_fee and self.manager_amount:
            total = money(self.total_amount)
            fee = money(self.platform_fee)
            manager = money(self.manager_amount)
            if fee + manager != total:
                raise ValidationError(
                    f"Split mismatch: platform_fee ({fee}) + manager_amount ({manager}) "
                    f"!= total_amount ({total})."
                )
            
    def mark_completed(self, paystack_reference, gateway_response=None, verified_amount=None):
        """
        Called from the Paystack webhook handler after verifying the payment.
        Creates the AdManagerEarning log record atomically.
        """
        with transaction.atomic():
            payment = (CampaignPayment.objects.select_for_update().select_related("campaign", "subaccount__ad_manager")).get(pk=self.pk)
            # Idempotent — safe to call twice from duplicate webhooks
            if payment.status == self.Status.COMPLETED:
                self._sync_form(payment)
                return
            if payment.status != self.Status.PENDING:
                raise ValidationError(f"Cannot complete a payment with status '{payment.status}'.")
            # Amount verification — catches any tampering between initialization and webhook
            if verified_amount is not None:
                if money(verified_amount) != money(payment.total_amount):
                    raise ValidationError(
                        f"Verified amount ({verified_amount}) does not match "
                        f"expected amount ({payment.total_amount})."
                    )
            payment.status = self.Status.COMPLETED
            payment.paystack_reference = paystack_reference
            payment.gateway_response = gateway_response or {}
            payment.completed_at = timezone.now()
            payment.save(update_fields=[
                "status", "paystack_reference", "gateway_response",
                "completed_at", "updated_at",
            ])
            # Create earning log for the ad manager
            AdManagerEarning.objects.create(
                payment=payment,
                ad_manager=payment.subaccount.ad_manager, 
                subaccount=payment.subaccount,
                amount=payment.manager_amount,
                platform_fee=payment.platform_fee,
                paystack_reference=paystack_reference,
            )
            self._sync_form(payment)
    
    def mark_failed(self, gateway_response=None):
        with transaction.atomic():
            payment = CampaignPayment.objects.select_for_update().get(pk=self.pk)
            if payment.status == self.Status.FAILED:
                self._sync_form(payment)
                return
            if payment.status == self.Status.COMPLETED:
                raise ValidationError("Completed payments cannot be marked failed.")
            payment.status = self.Status.FAILED
            payment.gateway_response = gateway_response or {}
            payment.save(update_fields=["status", "gateway_response", "updated_at"])
            self._sync_form(payment)
    
    def mark_refunded(self, refund_reference):
        """
        Called ONLY after Paystack confirms the refund via webhook.
        Do NOT call this before Paystack confirms the refund lives on
        Paystack's side, not in AdVerse.

        Refund flow:
        1. Ad manager or AdVerse initiates refund via Paystack API.
        2. Paystack processes and fires a refund webhook.
        3. Webhook handler calls this method with Paystack's refund reference.
        """
        with transaction.atomic():
            payment = CampaignPayment.objects.select_for_update().get(pk=self.pk)
            if payment.status == self.Status.REFUNDED:
                self._sync_form(payment)
                return
            if payment.status != self.Status.COMPLETED:
                raise ValidationError("Only completed payments can be refunded.")
            payment.status = self.Status.REFUNDED
            payment.refunded_at = timezone.now()
            payment.refund_reference = refund_reference
            payment.save(update_fields=["status", "refunded_at", "refund_reference", "updated_at"])
            self._sync_form(payment)

    def _sync_form(self, payment):
        self.status = payment.status
        self.paystack_reference = payment.paystack_reference
        self.gateway_response = payment.gateway_response
        self.completed_at = payment.completed_at
        self.refunded_at = payment.refunded_at
        self.refund_reference = payment.refund_reference

    def __str__(self):
        return f"CampaignPayment [{self.campaign.name}] NGN {self.total_amount} [{self.status}]"

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(total_amount__gte=0), name="campaign_payment_total_amount_positive",),
            models.CheckConstraint(condition=models.Q(platform_fee__gte=0), name="campaign_payment_platform_fee_non_negative",),
            models.CheckConstraint(condition=models.Q(manager_amount__gte=0), name="campaign_payment_manager_amount_positive",),
        ]
        indexes =  [
            models.Index(fields=["status"]),
            models.Index(fields=["reference"]),
            models.Index(fields=["paystack_reference"]),
        ]

# Ad Manager Earning Log
class AdManagerEarning(TimeStampedModel):
    # Read-only log of what an ad manager earned from a campaign payment.
    payment = models.ForeignKey(CampaignPayment, on_delete=models.PROTECT, related_name="manager_earnings",)
    ad_manager = models.ForeignKey("admanager.Admanager", on_delete=models.PROTECT, related_name="earnings",)
    subaccount = models.ForeignKey(AdManagerSubaccount, on_delete=models.PROTECT, related_name="earnings",)
    amount = models.DecimalField(max_digits=12, decimal_places=2)       # 90% they received
    platform_fee = models.DecimalField(max_digits=12, decimal_places=2) # 10% AdVerse took
    paystack_reference = models.CharField(max_length=120, blank=True)
    earned_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["payment", "ad_manager"],
                name="unique_manager_earning_per_payment",
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="earning_amount_positive",
            ),
        ]
        indexes = [
            models.Index(fields=["ad_manager", "earned_at"]),
            models.Index(fields=["paystack_reference"]),
        ]

# Payout Record (withdrawal history log)
class PayoutRecord(TimeStampedModel):
    """
    Log of withdrawals made directly by ad managers through Paystack.
    AdVerse does NOT initiate these, we only track and flag them.

    FRAUD CONTROLS:
    - is_flagged: set by a Celery task if the withdrawal looks suspicious.
      Triggers: large amount shortly after bank details change, withdrawal
      exceeds recent earnings, unusual frequency.
    - Flagged records send an internal alert to AdVerse staff but do NOT
      block the withdrawal — Paystack has already processed it.
    - flag() uses select_for_update() for consistency under concurrent flagging
    """
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        REVERSED = "reversed", "Reversed"

    ad_manager = models.ForeignKey("admanager.Admanager", on_delete=models.PROTECT, related_name="payout_records",)
    subaccount = models.ForeignKey( AdManagerSubaccount, on_delete=models.PROTECT,related_name="payout_records",)
    bank_name = models.CharField(max_length=120)
    account_number = models.CharField(max_length=20)
    account_name = models.CharField(max_length=180)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paystack_transfer_code = models.CharField(max_length=120, null=True, blank=True, unique=True,)
    paystack_reference = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    gateway_response = models.JSONField(default=dict, blank=True)
    is_flagged = models.BooleanField(default=False)
    flag_reason = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    @property
    def masked_account_number(self):
        return mask_account_number(self.account_number)
    
    def mark_success(self, paystack_transfer_code, paystack_reference="", gateway_response=None):
        with transaction.atomic():
            record = PayoutRecord.objects.select_for_update().get(pk=self.pk)
            if record.status == self.Status.SUCCESS:
                self._sync_form(record)
                return
            if record.status != self.Status.PENDING:
                raise ValidationError(
                    f"Cannot mark a '{record.status}' payout as successful."
                )
            record.status = self.Status.SUCCESS
            record.paystack_transfer_code = paystack_transfer_code
            record.paystack_reference = paystack_reference
            record.gateway_response = gateway_response or {}
            record.completed_at = timezone.now()
            record.save(update_fields=[
                "status", "paystack_transfer_code", "paystack_reference",
                "gateway_response", "completed_at", "updated_at",
            ])
            self._sync_form(record)

    def mark_failed(self, gateway_response=None):
        with transaction.atomic():
            record = PayoutRecord.objects.select_for_update().get(pk=self.pk)
            if record.status == self.Status.FAILED:
                self._sync_form(record)
                return
            if record.status == self.Status.SUCCESS:
                raise ValidationError("Successful payouts cannot be marked failed.")
            record.status = self.Status.FAILED
            record.gateway_response = gateway_response or {}
            record.save(update_fields=["status", "gateway_response", "updated_at"])
            self._sync_form(record)

    def flag(self, reason):
        """
        Mark this payout as suspicious for internal review.
        Uses select_for_update() to prevent concurrent flag overwrites.
        """
        with transaction.atomic():
            record = PayoutRecord.objects.select_for_update().get(pk=self.pk)
            record.is_flagged = True
            record.flag_reason = reason
            record.save(update_fields=["is_flagged", "flag_reason", "updated_at"])
            self.is_flagged = record.is_flagged
            self.flag_reason = record.flag_reason

    def _sync_form(self, record):
        self.status = record.status
        self.paystack_transfer_code = record.paystack_transfer_code
        self.paystack_reference = record.paystack_reference
        self.gateway_response = record.gateway_response
        self.completed_at = record.completed_at

    def __str__(self):
        return f"Payout [{self.ad_manager}] NGN {self.amount} [{self.status}]"

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="payout_amount_positive",
            ),
        ]
        indexes = [
            models.Index(fields=["ad_manager", "status"]),
            models.Index(fields=["status"]),
            models.Index(fields=["is_flagged"]),
            models.Index(fields=["paystack_transfer_code"]),
        ]

    
