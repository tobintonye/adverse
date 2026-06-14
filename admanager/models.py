from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
import uuid
from decimal import Decimal

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
    verification_requested = models.BooleanField(default=False)
    verification_requested_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='verified_ad_managers')
    is_active = models.BooleanField(default=True)
    rejection_reason = models.TextField(blank=True)
    total_billboards = models.PositiveIntegerField(default=0)
    total_campaigns_serverd = models.PositiveIntegerField(default=0)
    total_impressions = models.BigIntegerField(default=0)
    revenue = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    created_at = models.DateTimeField(auto_now_add=True)
    update_at = models.DateTimeField(auto_now=True)

    def verify(self, admin_user):
        self.verification_status = self.VerificationStatus.VERIFIED
        self.verification_requested = False
        self.verified_by = admin_user
        self.verified_at = timezone.now()
        self.rejection_reason = ''
        self.save(update_fields=['verification_status', 'verification_requested', 'verified_by', 'verified_at', 'rejection_reason', 'update_at'])

    def reject(self, admin_user, reason=''):
        self.verification_status = self.VerificationStatus.REJECTED
        self.verification_requested = False
        self.rejection_reason = reason
        self.save(update_fields=['verification_status', 'verification_requested', 'rejection_reason', 'update_at'])

    def suspend(self):
        self.verification_status = self.VerificationStatus.SUSPENDED
        self.is_active = False
        self.save(update_fields=['verification_status', 'is_active', 'update_at'])

    @property
    def received_campaigns(self):
        """Returns a queryset of all campaigns booking this manager's billboards."""
        from advertiser.models import Campaign  # Local import to prevent circular dependency
        return Campaign.objects.filter(campaign_slots__billboard__ad_manager=self).distinct()

    @property
    def total_campaigns_served(self):
        """Returns the dynamic count of campaigns served by this ad manager."""
        from advertiser.models import Campaign
        return self.received_campaigns.filter(
            status__in=[Campaign.Status.APPROVED, Campaign.Status.ACTIVE, Campaign.Status.COMPLETED]
        ).count()

    def calculate_revenue(self):
        from advertiser.models import Campaign, CampaignSlot
        slots = CampaignSlot.objects.filter(
            billboard__ad_manager=self,
            campaign__status__in=[Campaign.Status.APPROVED, Campaign.Status.ACTIVE, Campaign.Status.COMPLETED]
        ).select_related('campaign')
        
        total_rev = Decimal('0.00')
        for slot in slots:
            campaign = slot.campaign
            if campaign.actual_price > 0:
                ratio = campaign.admanager_split_price / campaign.actual_price
                total_rev += slot.slot_price * ratio
            else:
                total_rev += slot.slot_price * Decimal('0.70')
        return total_rev

    @property
    def total_withdrawn(self):
        approved_requests = self.withdrawal_requests.filter(status=WithdrawalRequest.Status.APPROVED)
        return approved_requests.aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')

    @property
    def pending_withdrawal(self):
        pending_requests = self.withdrawal_requests.filter(status=WithdrawalRequest.Status.PENDING)
        return pending_requests.aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')

    @property
    def available_balance(self):
        return self.revenue - self.total_withdrawn - self.pending_withdrawal
    
    def __str__(self):
        return self.business_name


class WithdrawalRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ad_manager = models.ForeignKey(Admanager, on_delete=models.CASCADE, related_name='withdrawal_requests')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    bank_details = models.TextField(help_text="Bank Name, Account Number, Account Name")
    notes = models.TextField(blank=True, help_text="Optional notes from the AdManager")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    admin_notes = models.TextField(blank=True, help_text="Notes/reason from the Admin")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.ad_manager.business_name} — ₦{self.amount:,.2f} ({self.status})"


class BankAccount(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ad_manager = models.ForeignKey(Admanager, on_delete=models.CASCADE, related_name='bank_accounts')
    bank_name = models.CharField(max_length=100)
    account_name = models.CharField(max_length=200)
    account_number = models.CharField(max_length=20)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_default', 'created_at']

    def save(self, *args, **kwargs):
        # If this is being set as default, clear others
        if self.is_default:
            BankAccount.objects.filter(ad_manager=self.ad_manager, is_default=True).exclude(pk=self.pk).update(is_default=False)
        # If it's the first account, auto-set as default
        elif not self.pk and not BankAccount.objects.filter(ad_manager=self.ad_manager).exists():
            self.is_default = True
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.bank_name} — {self.account_number} ({self.ad_manager.business_name})"