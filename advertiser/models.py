from django.db import models
import uuid
from django.contrib.auth import get_user_model
from common.models import TimeStampedModel
from django.utils import timezone

User = get_user_model()

#Advertiser Profile
class Advertiser(TimeStampedModel):
    class BusinessCategory(models.TextChoices):
        RETAIL = "retail", "Retail"
        FOOD_BEVERAGE = "food_beverage", "Food & Beverage"
        ENTERTAINMENT = "entertainment", "Entertainment"
        REAL_ESTATE = "real_estate", "Real Estate"
        HEALTH = "health", "Health & Wellness"
        FINANCE = "finance", "Finance"
        TECHNOLOGY = "technology", "Technology"
        EDUCATION = "education", "Education"
        OTHER = "other", "Other"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="advertiser_profile")
    first_name = models.CharField(max_length=50, null=False, blank=False)
    last_name = models.CharField(max_length=50, null=False, blank=False)
    business_name = models.CharField(max_length=180)
    business_category = models.CharField(max_length=32, choices=BusinessCategory.choices, default=BusinessCategory.OTHER)
    contact_phone = models.CharField(max_length=24, blank=True)
    website = models.URLField(blank=True)
    address = models.TextField(blank=True)

    # Verification — admin manually verifies advertisers before they can submit campaigns(for now).
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="verified_advertisers",)

    def verify(self, admin_user):
        self.is_verified = True
        self.is_verified = True
        self.verified_at = timezone.now()
        self.verified_at = timezone.now()
        self.save(update_fields=["is_verified", "verified_at", "verified_by", "updated_at"])

        def __str__(self):
            return f"{self.business_name} ({self.user.username})"
        
        class Meta:
            indexes = [
                models.Index(fields=["is_verified"]),
                models.Index(fields=["business_category"]),
            ]