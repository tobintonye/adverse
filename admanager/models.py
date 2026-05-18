from django.db import models
from django.contrib.auth import get_user_model
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
    is_active = models.BooleanField(default=True)
    rejection_reason = models.TextField(blank=True)
    total_billboards = models.PositiveIntegerField(default=0)
    total_campaigns_serverd = models.PositiveIntegerField(default=0)
    total_impressions = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    update_at = models.DateTimeField(auto_now=True)
    def __str__(self):
        return self.business_name