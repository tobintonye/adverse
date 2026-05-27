from django.db import models
import uuid
from django.contrib.auth import get_user_model
from common.models import TimeStampedModel
from django.utils import timezone
import mimetypes
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

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
    first_name = models.CharField(max_length=50, null=True, blank=False)
    last_name = models.CharField(max_length=50, null=True, blank=False)
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
            
def media_upload_path(instance, filename):
    # Organise S3 uploads by advertiser UUID -> advertiser/abc-111-uuid/media/... advertiser/xyz-222-uuid/media/..
    ext = filename.rsplit(".", 1)[-1].lower()
    return f"advertiser/{instance.advertiser_id}/media/{uuid.uuid4().hex}.{ext}"

def thumbnail_upload_path(instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower()
    return f"advertiser/{instance.advertiser_id}/thumbnails/{uuid.uuid4().hex}.{ext}"

# Media Library
class Media(TimeStampedModel):
    class MediaType(models.TextChoices):
        IMAGE = "image", "Image"
        VIDEO = "video", "Video"
    
    class Status(models.TextChoices): 
        PENDING = "pending", "Pending Review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    ALLOWED_IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "webp"]
    ALLOWED_VIDEO_EXTENSIONS = ["mp4", "mov", "webm"]
    ALLOWED_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS + ALLOWED_VIDEO_EXTENSIONS

    MAX_IMAGE_SIZE_MB = 10
    MAX_VIDEO_SIZE_MB = 500

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    advertiser = models.ForeignKey(Advertiser, on_delete=models.CASCADE, related_name="media_files")
    title = models.CharField(max_length=180)
    file = models.FileField(
        upload_to=media_upload_path, 
        validators=[FileExtensionValidator(allowed_extensions=ALLOWED_EXTENSIONS)]
    )
    media_type = models.CharField(max_length=10, choices=MediaType.choices, blank=False, null=False)
    duration_seconds = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Required for video. Duration the ad will play on screen.",
    )
    file_size_bytes = models.PositiveBigIntegerField(editable=False, default=0)
    thumbnail = models.ImageField(upload_to=thumbnail_upload_path, null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    rejection_reason = models.TextField(blank=True)

    # Approval trail
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_media")
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "media"
        indexes = [
            models.Index(fields=["advertiser", "status"]), 
            models.Index(fields=["media_type"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.media_type}) — {self.status}"
    
    def approve(self, reviewer): 
        self.status = self.Status.APPROVED
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.rejection_reason = ""
        self.save(update_fields=[
            "status", "reviewed_by", "reviewed_at", "rejection_reason", "updated_at"
        ])

    def reject(self, reviewer, reason=""):
        self.status = self.Status.REJECTED
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.rejection_reason = reason
        self.save(update_fields=[
            "status", "reviewed_by", "reviewed_at", "rejection_reason", "updated_at"
        ])

    # validation 
    def clean(self):
        # Fallback model validation
        super().clean()
        if not self.file:
            return 
        self.file_size_bytes = self.file.size
        file_size_mb = self.file_size_bytes / (1024 * 1024)

        if self.media_type == self.MediaType.IMAGE and file_size_mb > self.MAX_IMAGE_SIZE_MB:
            raise ValidationError({"file": f"Images cannot exceed {self.MAX_IMAGE_SIZE_MB}MB."})
        if self.media_type == self.MediaType.VIDEO:
            if file_size_mb > self.MAX_VIDEO_SIZE_MB:
                raise ValidationError({"file": f"Videos cannot exceed {self.MAX_VIDEO_SIZE_MB}MB."})
            if not self.duration_seconds: 
                raise ValidationError({"duration_seconds": "Duration is required for video media."})
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def file_size_mb(self):
        return round(self.file_size_bytes / (1024 * 1024), 2)
    
    @property
    def is_approved(self):
        return self.status == self.Status.APPROVED
 
    @property
    def file_url(self):
        return self.file.url if self.file else None