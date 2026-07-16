from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from common.models import TimeStampedModel

User = get_user_model()

NAIRA = Decimal("0.01")
PLATFORM_FEE_PERCENT = Decimal("30.00")  # AdVerse takes 30%, ad manager gets 70%


def money(value):
    """Normalize and validate a monetary amount."""
    amount = Decimal(str(value)).quantize(NAIRA, ROUND_HALF_UP)
    if amount <= 0:
        raise ValidationError("Amount must be positive.")
    return amount


def compute_split(total_amount):
    """
    Returns (platform_fee, ad_manager_amount) for a given total.
    Always uses PLATFORM_FEE_PERCENT so the split is consistent everywhere.

    AdVerse: 30% | Ad manager: 70%
    """
    total = money(total_amount)
    fee = (total * PLATFORM_FEE_PERCENT / Decimal("100")).quantize(
        NAIRA, rounding=ROUND_HALF_UP
    )
    manager_amount = total - fee
    return fee, manager_amount


def mask_account_number(account_number: str) -> str:
    """Returns last 4 digits masked: ******1234"""
    if not account_number:
        return ""
    return f"******{account_number[-4:]}"

# Ad Manager Subaccount
class AdManagerSubaccount(TimeStampedModel):
    """
    One Paystack subaccount per ad manager.
    account_number stores only the last 4 digits — the full number is never
    persisted locally. Use subaccount_code to retrieve full details from
    Paystack's API when needed.
    """
    ad_manager = models.OneToOneField(
        "admanager.Admanager",
        on_delete=models.PROTECT,
        related_name="paystack_subaccount",
    )
    subaccount_code = models.CharField(max_length=120, unique=True)
    business_name = models.CharField(max_length=180) # to be changed 
    bank_name = models.CharField(max_length=120)
    bank_code = models.CharField(max_length=10)
    # Only the last 4 digits are stored. The full account number is never
    # persisted — Paystack holds the authoritative copy via subaccount_code.
    account_number_last4 = models.CharField(max_length=4) # to be changed 
    account_name = models.CharField(max_length=180)
    settlement_bank = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    gateway_response = models.JSONField(default=dict, blank=True)

    @property
    def masked_account_number(self) -> str:
        """Returns: ******1234"""
        if not self.account_number_last4:
            return ""
        return f"******{self.account_number_last4}"

    @property
    def is_verified(self) -> bool:
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

    def update_bank_details(self, bank_name, bank_code, account_number_last4, account_name, updated_by):
        """
        Update bank details and log the change with masked old values.
        Clears verified_at — subaccount must be re-verified before accepting payments.
        Caller must also update the subaccount on Paystack via their API.
        """
        masked_old = {
            "bank_name": self.bank_name,
            "bank_code": self.bank_code,
            "account_number": self.masked_account_number,
            "account_name": self.account_name,
        }
        with transaction.atomic():
            self.bank_name = bank_name
            self.bank_code = bank_code
            self.account_number_last4 = account_number_last4
            self.account_name = account_name
            self.verified_at = None  # must re-verify after bank change
            self.save(update_fields=[
                "bank_name", "bank_code", "account_number_last4",
                "account_name", "verified_at", "updated_at",
            ])
            AdManagerSubaccountAuditLog.objects.create(
                subaccount=self,
                event=AdManagerSubaccountAuditLog.Event.BANK_DETAILS_CHANGED,
                changed_by=updated_by,
                note=f"Previous details: {masked_old}",
            )

    def mark_verified(self, changed_by=None):
        """Call after confirming bank details with Paystack name enquiry."""
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
        Call before initializing a Paystack transaction for a campaign
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
        
    def sync_with_paystack(self, changed_by=None):
        """
        Verify this subaccount still exists on Paystack.
        Only deactivates if Paystack explicitly returns active=False.
        Network errors and timeouts are ignored — don't punish the ad manager
        for Paystack being temporarily unreachable.
        """
        from payments.services import _paystack_get
        from django.core.exceptions import ValidationError as DjangoValidationError

        try:
            response = _paystack_get(
                f"https://api.paystack.co/subaccount/{self.subaccount_code}"
            )
            data = response.get("data", {})
            paystack_active = data.get("active", True)  # default True — assume active if missing

            if paystack_active is False and self.is_active:
                self.deactivate(
                    reason="Deactivated because subaccount is no longer active on Paystack.",
                    changed_by=changed_by,
                )
            elif paystack_active and not self.is_active:
                # Paystack says active but we have it deactivated — re-sync
                self.reactivate(changed_by=changed_by)

        except DjangoValidationError:
            # Paystack API error — don't deactivate, just log
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                "sync_with_paystack: could not reach Paystack for subaccount %s — skipping.",
                self.subaccount_code,
            )
    def __str__(self):
        return f"Subaccount [{self.ad_manager}] {self.subaccount_code}"

    class Meta:
        indexes = [
            models.Index(fields=["is_active"]),
            models.Index(fields=["subaccount_code"]),
        ]

# Subaccount Audit Log
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

    subaccount = models.ForeignKey(
        AdManagerSubaccount,
        on_delete=models.PROTECT,
        related_name="audit_logs",  
    )
    event = models.CharField(max_length=32, choices=Event.choices)
    changed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="subaccount_audit_logs")
    note = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        # Immutable — block any update attempt.
        # Check is done inside a select_for_update to reduce (but not fully
        # eliminate) the concurrent-write race. The real guarantee is that
        # callers should never hold a reference long enough to retry a save.
        if self.pk:
            with transaction.atomic():
                exists = (
                    AdManagerSubaccountAuditLog.objects
                    .select_for_update()
                    .filter(pk=self.pk)
                    .exists()
                )
                if exists:
                    raise ValidationError("Subaccount audit logs are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Subaccount audit logs cannot be deleted.")

    def __str__(self):
        return (
            f"AuditLog [{self.subaccount.ad_manager}] "
            f"{self.event} @ {self.created_at}"
        )

    class Meta:
        indexes = [
            models.Index(fields=["subaccount", "created_at"]),
            models.Index(fields=["event"]),
        ]

# Campaign Payment
class CampaignPayment(TimeStampedModel):
    """
    Records the outcome of an advertiser paying for a campaign via Paystack.

    Flow (Paystack handles the split automatically):
    1. AdVerse initializes a Paystack transaction with the ad manager's
       subaccount_code. Paystack splits automatically:
         - platform_fee (30%) → AdVerse main Paystack account
         - manager_amount (70%) → Ad manager's Paystack subaccount
    2. Paystack fires a charge.success webhook.
    3. AdVerse verifies the webhook signature and re-verifies with Paystack API.
    4. mark_completed() is called, creating the AdManagerEarning log atomically.

    AdVerse never holds the money. Paystack does the split at transaction time.

    FRAUD CONTROLS:
    - subaccount.assert_ready_for_payment() must be called before initializing.
    - verified_amount is checked against total_amount in mark_completed().
    - paystack_reference ties this record to an auditable Paystack transaction.
    - split integrity is enforced in save(): platform_fee + manager_amount == total_amount.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    campaign = models.OneToOneField( "advertiser.Campaign", on_delete=models.PROTECT, related_name="payment")
    subaccount = models.ForeignKey( AdManagerSubaccount, on_delete=models.PROTECT, related_name="campaign_payments")
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    platform_fee = models.DecimalField(max_digits=12, decimal_places=2)   # 30% → AdVerse
    manager_amount = models.DecimalField(max_digits=12, decimal_places=2) # 70% → ad manager
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    reference = models.CharField(max_length=120, unique=True)        # AdVerse-generated
    paystack_reference = models.CharField(max_length=120, blank=True) # Paystack's reference
    gateway_response = models.JSONField(default=dict, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    refund_reference = models.CharField(max_length=120, blank=True)

    def save(self, *args, **kwargs):
        # Enforce split integrity on every save, not just form submissions.
        # clean() is only called by ModelForm/full_clean() — not .create()/.save().
        if self.total_amount and self.platform_fee and self.manager_amount:
            total = money(self.total_amount)
            fee = money(self.platform_fee)
            manager = money(self.manager_amount)
            if fee + manager != total:
                raise ValidationError(
                    f"Split mismatch: platform_fee ({fee}) + manager_amount ({manager}) "
                    f"!= total_amount ({total})."
                )
        super().save(*args, **kwargs)

    def mark_completed(self, paystack_reference, gateway_response=None, verified_amount=None):
        """
        Called from the Paystack webhook handler after verifying the payment.
        Creates the AdManagerEarning log record atomically.
        Idempotent — safe to call twice from duplicate webhooks.
        """
        with transaction.atomic():
            payment = (
                CampaignPayment.objects
                .select_for_update()
                .select_related("campaign", "subaccount__ad_manager")
                .get(pk=self.pk)
            )
            if payment.status == self.Status.COMPLETED:
                self._sync_from(payment)
                return
            if payment.status != self.Status.PENDING:
                raise ValidationError(
                    f"Cannot complete a payment with status '{payment.status}'."
                )
            # Amount verification — catches any tampering between init and webhook
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
            AdManagerEarning.objects.create(
                payment=payment,
                ad_manager=payment.subaccount.ad_manager,
                subaccount=payment.subaccount,
                amount=payment.manager_amount,
                platform_fee=payment.platform_fee,
                paystack_reference=paystack_reference,
            )
            campaign = payment.campaign
            today = timezone.now().date()
            if campaign.start_date <= today:
                from advertiser.models import Campaign as CampaignModel
                if campaign.status == CampaignModel.Status.APPROVED:
                    campaign.status = CampaignModel.Status.ACTIVE
                    campaign.save(update_fields=["status", "updated_at"])
            # If start_date is in the future, leave as APPROVED —
            # Celery's activate_due_campaigns will pick it up on the right day.
            self._sync_from(payment)

        # Emails fired AFTER transaction commits
        from adverseproject.emails import send_adverse_email
        site_url = getattr(settings, "SITE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    
        first_slot = payment.campaign.campaign_slots.select_related("billboard").first()
        billboard_name = first_slot.billboard.name if first_slot else "Your billboard"
    
        # Payment confirmed → advertiser
        send_adverse_email(
            template="payment_confirmed",
            to=payment.campaign.advertiser.user.email,
            context={
                "advertiser_name": payment.campaign.advertiser.user.get_full_name()
                    or payment.campaign.advertiser.user.email,
                "campaign_name": payment.campaign.name,
                "amount": f"{payment.total_amount:,.2f}",
                "reference": payment.reference,
                "start_date": payment.campaign.start_date.strftime("%b %d, %Y"),
                "end_date": payment.campaign.end_date.strftime("%b %d, %Y"),
                "billboard_name": billboard_name,
                "campaign_url": f"{site_url}/advertiser/campaigns/{payment.campaign.id}/",
            },
        )
    
        # Earnings credited → ad manager
        send_adverse_email(
            template="earnings_credited",
            to=payment.subaccount.ad_manager.user.email,
            context={
                "manager_name": payment.subaccount.ad_manager.user.get_full_name()
                    or payment.subaccount.ad_manager.user.email,
                "campaign_name": payment.campaign.name,
                "amount": f"{payment.manager_amount:,.2f}",
                "platform_fee": f"{payment.platform_fee:,.2f}",
                "billboard_name": billboard_name,
                "reference": paystack_reference,
                "withdrawals_url": f"{site_url}/admanager/withdrawals/",
            },
        )
    def mark_failed(self, gateway_response=None):
        with transaction.atomic():
            payment = CampaignPayment.objects.select_for_update().get(pk=self.pk)
            if payment.status == self.Status.FAILED:
                self._sync_from(payment)
                return
            if payment.status == self.Status.COMPLETED:
                raise ValidationError("Completed payments cannot be marked failed.")
            payment.status = self.Status.FAILED
            payment.gateway_response = gateway_response or {}
            payment.save(update_fields=["status", "gateway_response", "updated_at"])
            self._sync_from(payment)

    def mark_refunded(self, refund_reference):
        """
        Called ONLY after Paystack confirms the refund via webhook.
        Do NOT call this before Paystack confirms — the refund lives on
        Paystack's side, not in AdVerse.

        Refund flow:
        1. AdVerse initiates refund via Paystack API (services.py).
        2. Paystack processes and fires a refund webhook.
        3. Webhook handler calls this method with Paystack's refund reference.
        """
        with transaction.atomic():
            payment = CampaignPayment.objects.select_for_update().get(pk=self.pk)
            if payment.status == self.Status.REFUNDED:
                self._sync_from(payment)
                return
            if payment.status != self.Status.COMPLETED:
                raise ValidationError("Only completed payments can be refunded.")
            payment.status = self.Status.REFUNDED
            payment.refunded_at = timezone.now()
            payment.refund_reference = refund_reference
            payment.save(update_fields=[
                "status", "refunded_at", "refund_reference", "updated_at"
            ])
            self._sync_from(payment)

    def _sync_from(self, payment):
        """Sync in-memory instance fields from the DB-fresh copy."""
        self.status = payment.status
        self.paystack_reference = payment.paystack_reference
        self.gateway_response = payment.gateway_response
        self.completed_at = payment.completed_at
        self.refunded_at = payment.refunded_at
        self.refund_reference = payment.refund_reference

    def __str__(self):
        return (
            f"CampaignPayment [{self.campaign.name}] "
            f"NGN {self.total_amount} [{self.status}]"
        )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(total_amount__gt=0),
                name="campaign_payment_total_amount_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(platform_fee__gte=0),
                name="campaign_payment_platform_fee_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(manager_amount__gt=0),
                name="campaign_payment_manager_amount_positive",
            ),
        ]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["reference"]),
            models.Index(fields=["paystack_reference"]),
        ]

# Ad Manager Earning Log
class AdManagerEarning(TimeStampedModel):
    """Read-only log of what an ad manager earned from a campaign payment."""

    payment = models.ForeignKey(CampaignPayment, on_delete=models.PROTECT, related_name="manager_earnings" )
    ad_manager = models.ForeignKey( "admanager.Admanager", on_delete=models.PROTECT, related_name="earnings")
    subaccount = models.ForeignKey( AdManagerSubaccount, on_delete=models.PROTECT, related_name="earnings")
    amount = models.DecimalField(max_digits=12, decimal_places=2)       # 70% ad manager received
    platform_fee = models.DecimalField(max_digits=12, decimal_places=2) # 30% AdVerse took
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

# Payout Record
class PayoutRecord(TimeStampedModel):
    """
    Log of withdrawals made directly by ad managers through Paystack.
    AdVerse does NOT initiate these — we only track and flag them.

    account_number stores only the last 4 digits for display purposes.
    The full account number is never stored locally.

    FRAUD CONTROLS:
    - is_flagged: set by a Celery task if the withdrawal looks suspicious.
      Triggers: large amount shortly after bank details change, withdrawal
      exceeds recent earnings, unusual frequency.
    - Flagged records send an internal alert to AdVerse staff but do NOT
      block the withdrawal — Paystack has already processed it.
    - flag() uses select_for_update() for safety under concurrent flagging.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"
        REVERSED = "reversed", "Reversed"

    ad_manager = models.ForeignKey( "admanager.Admanager", on_delete=models.PROTECT, related_name="payout_records")
    subaccount = models.ForeignKey( AdManagerSubaccount, on_delete=models.PROTECT, related_name="payout_records")
    bank_name = models.CharField(max_length=120)
    # Last 4 digits only — full account number is never stored locally.
    account_number_last4 = models.CharField(max_length=4)
    account_name = models.CharField(max_length=180)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paystack_transfer_code = models.CharField(
        max_length=120, null=True, blank=True, unique=True
    )
    paystack_reference = models.CharField(max_length=120, blank=True)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING
    )
    gateway_response = models.JSONField(default=dict, blank=True)
    is_flagged = models.BooleanField(default=False)
    flag_reason = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    @property
    def masked_account_number(self) -> str:
        """Returns: ******1234"""
        if not self.account_number_last4:
            return ""
        return f"******{self.account_number_last4}"

    def mark_success(
        self, paystack_transfer_code, paystack_reference="", gateway_response=None
    ):
        with transaction.atomic():
            record = PayoutRecord.objects.select_for_update().get(pk=self.pk)
            if record.status == self.Status.SUCCESS:
                self._sync_from(record)
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
            self._sync_from(record)

    def mark_failed(self, gateway_response=None):
        with transaction.atomic():
            record = PayoutRecord.objects.select_for_update().get(pk=self.pk)
            if record.status == self.Status.FAILED:
                self._sync_from(record)
                return
            if record.status == self.Status.SUCCESS:
                raise ValidationError("Successful payouts cannot be marked failed.")
            record.status = self.Status.FAILED
            record.gateway_response = gateway_response or {}
            record.save(update_fields=["status", "gateway_response", "updated_at"])
            self._sync_from(record)

    def flag(self, reason: str):
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

    def _sync_from(self, record):
        """Sync in-memory instance fields from the DB-fresh copy."""
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