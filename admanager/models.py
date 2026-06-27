from django.db import models
from django.contrib.auth import get_user_model
import uuid
from django.core.exceptions import ValidationError
from django.utils import timezone

User = get_user_model()

# Billboard owner / screen operator profile
class Admanager(models.Model): 
    class VerificationStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"
        SUSPENDED = "suspended", "Suspended"
    
    class BusinessType(models.TextChoices): 
        INDIVIDUAL = "individual", "Individual"
        COMPANY = "company", "Company"
        
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='ad_manager')
   
    business_name = models.CharField(max_length=200, blank=False, null=False)
    business_type = models.CharField(max_length=20, choices=BusinessType.choices, default=BusinessType.INDIVIDUAL)
    company_registration_number = models.CharField(max_length=100, blank=True)
    tax_identification_number = models.CharField(max_length=100, blank=True)
    business_email = models.EmailField()
    business_phone = models.CharField(max_length = 20)
    website = models.URLField(blank=True)

    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100,default="Nigeria")
   
    verification_status = models.CharField(max_length=20, choices=VerificationStatus.choices, default=VerificationStatus.PENDING)
    is_active = models.BooleanField(default=True)
    rejection_reason = models.TextField(blank=True)
    suspension_reason = models.TextField(blank=True)

    # Audit trail — who changed the status and when
    verified_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="verified_ad_managers")
    verified_at  = models.DateTimeField(null=True, blank=True)
    verification_requested = models.BooleanField(default=False)
    verification_requested_at = models.DateTimeField(null=True, blank=True)
    suspended_by = models.ForeignKey(User, null=True, blank=True,on_delete=models.SET_NULL, related_name="suspended_ad_managers",)
    suspended_at = models.DateTimeField(null=True, blank=True)

    # financials 
    # Commission rate — platform takes this % from each campaign earned by this manager

    # Default matches PLATFORM_FEE_PERCENT in payments/models.py (10%).
    # Can be overridden per manager (e.g. premium partners pay lower commission).
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, default=10.00,help_text="Platform commission percentage taken from this manager's earnings. Default 10%.")

    bank_name = models.CharField(max_length=120, blank=True)
    account_number = models.CharField(max_length=20, blank=True)
    account_name = models.CharField(max_length=180, blank=True)
    bank_code = models.CharField(max_length=10, blank=True, help_text="Paystack bank code for transfers.")
    
    # NEW: Store the Paystack Recipient Code for easier API transfers
    recipient_code = models.CharField(max_length=50, unique=True, blank=True, null=True, help_text="Paystack RCP code.")


    total_billboards = models.PositiveIntegerField(default=0)
    total_campaigns_serverd = models.PositiveIntegerField(default=0)
    total_impressions = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_verified(self):
        return self.verification_status == self.VerificationStatus.VERIFIED
    
    @property
    def has_bank_account(self):
        return hasattr(self, "paystack_subaccount")
    
    @property
    def received_campaigns(self):
        """Returns a queryset of all campaigns booking this manager's billboards."""
        from advertiser.models import Campaign  # Local import to prevent circular dependency
        return Campaign.objects.filter(campaign_slots__billboard__ad_manager=self).distinct()
    
    @property
    def pending_review_campaigns(self):
        from advertiser.models import Campaign
        return self.received_campaigns.filter(
            status=Campaign.Status.PENDING_MANAGER_REVIEW
        )
    
    @property
    def active_campaigns(self):
        # Currently running campaigns on this manager's billboards
        from advertiser.models import Campaign
        return self.received_campaigns.filter(
            status=Campaign.Status.ACTIVE
        )
    
    #Global Tech Admin verifies the ad manager account
    def verify(self, admin_user):
        if self.verification_status == self.VerificationStatus.VERIFIED:
            raise ValidationError("Account is already verified.")
        self.verification_status = self.VerificationStatus.VERIFIED
        self.is_active = True
        self.verified_by = admin_user
        self.verified_at = timezone.now()
        self.rejection_reason= ""
        self.verification_requested = False 
        self.save(update_fields=[
            "verification_status", "is_active",
            "verified_by", "verified_at",
            "rejection_reason", "verification_requested", "updated_at",
        ])
    
    def reject(self, admin_user, reason=""):
        if not reason.strip():
            raise ValidationError("A rejection reason is required.")
        if self.verification_status not in [self.VerificationStatus.PENDING, self.VerificationStatus.VERIFIED]:
            raise ValidationError("Account cannot be rejected from its current status.")
        self.verification_status = self.VerificationStatus.REJECTED
        self.is_active = False
        self.rejection_reason = reason
        self.verification_requested = False
        self.save(update_fields=[
            "verification_status", "is_active",
            "rejection_reason", "verification_requested", "updated_at",
        ])

    def suspend(self, admin_user, reason=""):
        if not reason.strip():
            raise ValidationError("A suspension reason is required.")
        if self.verification_status != self.VerificationStatus.VERIFIED:
            raise ValidationError("Only verified accounts can be suspended.")
        self.verification_status = self.VerificationStatus.SUSPENDED
        self.is_active = False
        self.suspension_reason = reason
        self.suspended_by = admin_user
        self.suspended_at = timezone.now()
        self.save(update_fields=[
            "verification_status", "is_active",
            "suspension_reason", "suspended_by", "suspended_at",
            "updated_at",
        ])        
    
    def reinstate(self, admin_user):
        if self.verification_status != self.VerificationStatus.SUSPENDED:
            raise ValidationError("Only suspended accounts can be reinstated.")
        self.verification_status = self.VerificationStatus.VERIFIED
        self.is_active = True
        self.suspension_reason = ""
        self.save(update_fields=[
            "verification_status", "is_active",
            "suspension_reason", "updated_at",
        ])

    # admanager to request a verification 
    def request_verification(self):
        """
        Ad manager flags their account as ready for admin review.
        Only meaningful from PENDING — already verified/rejected/suspended
        accounts shouldn't be re-flagged via this path.
        """
        if self.verification_status != self.VerificationStatus.PENDING:
            raise ValidationError(
                "Only accounts pending verification can request a review."
            )
        if self.verification_requested:
            raise ValidationError("A verification request has already been submitted.")

        self.verification_requested = True
        self.verification_requested_at = timezone.now()
        self.save(update_fields=["verification_requested", "verification_requested_at", "updated_at"])

    def __str__(self):
        return f"{self.business_name} [{self.verification_status}]"
    
    class Meta:
        verbose_name    = "Ad Manager"
        verbose_name_plural = "Ad Managers"
        indexes = [
            models.Index(fields=["verification_status"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["business_type"]),
            models.Index(fields=["country", "state", "city"]),
        ]