from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
import uuid

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
    
    def __str__(self):
        return self.business_name