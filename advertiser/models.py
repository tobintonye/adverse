from django.db import models, transaction
import uuid
import hashlib
from decimal import Decimal
from django.contrib.auth import get_user_model
from common.models import TimeStampedModel
from django.utils import timezone
import datetime 
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.core.validators import FileExtensionValidator
from device.models import Billboard
from django.core.validators import MaxValueValidator, MinValueValidator

User = get_user_model()

# Advertiser Profile
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
    first_name = models.CharField(max_length=50, blank=False)
    last_name = models.CharField(max_length=50, blank=False)
    business_name = models.CharField(max_length=180, null=False, blank=False)
    business_category = models.CharField(max_length=32, choices=BusinessCategory.choices, default=BusinessCategory.OTHER)
    contact_phone = models.CharField(max_length=24, blank=True)
    website = models.URLField(blank=True)
    address = models.TextField(blank=True)

    # Verification — admin manually verifies advertisers before they can submit campaigns(for now).
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="verified_advertisers")
    verification_requested = models.BooleanField(default=False)
    verification_requested_at = models.DateTimeField(null=True, blank=True)

    def verify(self, admin_user):
        self.is_verified = True
        self.verification_requested = False
        self.verified_by = admin_user
        self.verified_at = timezone.now()
        self.save(update_fields=["is_verified", "verification_requested", "verified_at", "verified_by", "updated_at"])

    def request_verification(self):
        if self.is_verified:
            raise ValidationError("Your account is already verified.")
        if self.verification_requested:
            raise ValidationError("You have already submitted a verification request. Please wait for admin review.")
        self.verification_requested = True
        self.verification_requested_at = timezone.now()
        self.save(update_fields=["verification_requested", "verification_requested_at", "updated_at"])
        
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
        ADMIN_APPROVED = "admin_approved",  "Admin Approved"
        FULLY_APPROVED = "fully_approved",  "Fully Approved" # final approval by the billboard owner
        REJECTED = "rejected", "Rejected"

    class TranscodeStatus(models.TextChoices):
        PENDING = "pending", "Not processed yet"
        PROCESSING = "processing", "Processing"
        DONE = "done", "Ready for playback"
        FAILED = "failed", "Processing failed"

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
    file_hash = models.CharField(max_length=64, blank=True, help_text="SHA-256 of the uploaded file. Used to detect duplicates.") # used to detect is a file already exists
    media_type = models.CharField(max_length=10, choices=MediaType.choices, blank=False, null=False)
    duration_seconds = models.PositiveIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(90)],
        help_text="Required for video. Duration the ad will play on screen.", # something to think about because someone can place a 5mins ad that will be too long. the highest should be
    )
    file_size_bytes = models.PositiveBigIntegerField(editable=False, default=0)
    thumbnail = models.ImageField(upload_to=thumbnail_upload_path, null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    rejection_reason = models.TextField(blank=True)


    """
    Media file can be fully_approved and still not be safe to send to a billboard box if it's an incompatible codec/resolution the device's
    hardware decoder can't handle. This is what get_playlist_for_billboard() gates on in addition to approval status.
    """
    processed_file = models.FileField(upload_to=media_upload_path, null=True, blank=True, help_text="Transcoded/normalized version actually served to devices. Empty if the original already met spec.")
    transcode_status = models.CharField(max_length=12, choices=TranscodeStatus .choices, default=TranscodeStatus.PENDING, help_text="Whether this file is verified safe to decode on billboard hardware.",)
    transcode_error = models.TextField(blank=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    video_codec = models.CharField(max_length=32, blank=True)

    # Approval trail
    # reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_media")
    #reviewed_at = models.DateTimeField(null=True, blank=True)
    admin_reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_media_admin")
    admin_reviewed_at = models.DateTimeField(null=True, blank=True)
    manager_reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_media_manager") 
    manager_reviewed_at = models.DateTimeField(null=True, blank=True)
 
    class Meta:
        verbose_name_plural = "media"
        indexes = [
            models.Index(fields=["advertiser", "status"]), 
            models.Index(fields=["media_type"]),
            models.Index(fields=["status"]),
        ]

        constraints = [
            models.UniqueConstraint(
                fields=["advertiser", "file_hash"],
                name="unique_media_per_advertiser",
            )
        ]

    def __str__(self):
        return f"{self.title} ({self.media_type}) — {self.status}"
    
    """
        Global Tech Admin approves the content.
        Media is now usable in a campaign but NOT yet live.
    """
    def approve(self, admin_user): 
        if self.status != self.Status.PENDING:
            raise ValidationError("Only pending media can be admin-approved.")
        self.status = self.Status.ADMIN_APPROVED
        self.admin_reviewed_by = admin_user
        self.admin_reviewed_at = timezone.now()
        self.rejection_reason = ""
        self.save(update_fields=[
            "status", "admin_reviewed_by", "admin_reviewed_at", "rejection_reason", "updated_at"
        ])

    """
        Ad Manager gives final approval.
        Media is now fully live — playing on the billboard.
        Called automatically when the ad manager approves the campaign.
    """
    def fully_approve(self, manager_user):
        if self.status == self.Status.FULLY_APPROVED:
            return
        if self.status != self.Status.ADMIN_APPROVED:
             raise ValidationError("Media must be admin-approved before manager approval.")
        self.status = self.Status.FULLY_APPROVED 
        self.manager_reviewed_by = manager_user
        self.manager_reviewed_at = timezone.now()
        self.save(update_fields=[
            "status", "manager_reviewed_by", "manager_reviewed_at", "updated_at",
        ])

    def reject(self, reviewer, reason=""):
        # Can be called by admin or ad manager
        if not reason.strip():
            raise ValidationError("A rejection reason is required.")
        self.status = self.Status.REJECTED
        self.rejection_reason = reason
        # Track which stage rejected it
        if reviewer.is_staff:
            self.admin_reviewed_by = reviewer
            self.admin_reviewed_at = timezone.now()
            self.save(update_fields=[
                "status", "rejection_reason",
                "admin_reviewed_by", "admin_reviewed_at", "updated_at",
            ])
        else:
            self.manager_reviewed_by = reviewer
            self.manager_reviewed_at = timezone.now()
            self.save(update_fields=[
                "status", "rejection_reason",
                "manager_reviewed_by", "manager_reviewed_at", "updated_at",
            ])

    # validation 
    def clean(self):
        # Fallback model validation
        super().clean()
        if self.media_type == self.MediaType.IMAGE and self.duration_seconds is not None:
             raise ValidationError({ "duration_seconds": "Images cannot have a playing duration set." })
        if self.media_type == self.MediaType.VIDEO and not self.duration_seconds: 
            raise ValidationError({ "duration_seconds": "Duration is required for video media." })

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

        # Calculate file hash and check for duplicates by creating a unique fingerprint (hash) of the file data 6
        if hasattr(self, 'advertiser') and self.advertiser:
            if not self.file_hash:
                hasher = hashlib.sha256() # generate a unique 64-character text ID based on the file's contents
                self.file.seek(0)
                for chunk in self.file.chunks():
                    hasher.update(chunk)
                self.file_hash = hasher.hexdigest()
                self.file.seek(0)
            
            # Check uniqueness
            duplicate = Media.objects.filter(advertiser=self.advertiser, file_hash=self.file_hash)
            if self.pk:
                duplicate = duplicate.exclude(pk=self.pk)
            if duplicate.exists():
                raise ValidationError("You have already uploaded this file. Check your media library.")
        
    def save(self, *args, **kwargs):
        is_new = self._state.adding
        update_fields = kwargs.get("update_fields")

        if update_fields is not None:
            file_changed = "file" in update_fields
        else:
            file_changed = is_new
            if not is_new and self.pk:
                previous = Media.objects.filter(pk=self.pk).values_list("file", flat=True).first()
                file_changed = previous != self.file.name
        self.full_clean(validate_unique=False, validate_constraints=False)
        super().save(*args, **kwargs)
        if file_changed:
            from .tasks import process_media_task
            transaction.on_commit(lambda: process_media_task.delay(str(self.id)))

    @property
    def file_size_mb(self):
        return round(self.file_size_bytes / (1024 * 1024), 2)
    
    @property
    def is_approved(self):
        return self.status == self.Status.ADMIN_APPROVED
 
    @property
    def is_live(self):
        return self.status == self.Status.FULLY_APPROVED

    @property
    def is_playable(self): 
        # Check whether this file may ever reach a billboard device, independent of admin/manager approval.
        return self.transcode_status == self.TranscodeStatus.DONE

    @property 
    def playback_url(self): 
        """What the device actually downloads — the transcoded version if one exists, otherwise the original (it only reaches DONE without a
        processed_file if the original already met spec)."""
        if self.processed_file:
            return self.processed_file.url
        return self.file.url if self.file else None

    @property
    def file_url(self):
        return self.file.url if self.file else None

# owned by Advertiser, books ad_manager's Billboards
class Campaign(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING_ADMIN_REVIEW = "pending_admin_review", "Pending Admin Review"
        PENDING_MANAGER_REVIEW = "pending_manager_review", "Pending Manager Review"
        APPROVED = "approved", "Approved"
        APPROVAL_EXPIRED = "approval_expired", "Approval Expired"  
        REJECTED = "rejected", "Rejected"
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    advertiser  = models.ForeignKey(Advertiser, on_delete=models.CASCADE, related_name="campaigns")
    name = models.CharField(max_length=100)
    media = models.ForeignKey(Media, on_delete=models.PROTECT, related_name="campaigns") #limit_choices_to={"status": [Media.Status.ADMIN_APPROVED, Media.Status.FULLY_APPROVED]}) # only admin approved media can be used when building a campaign
    # Schedule
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    duration_days = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(90)], help_text="How many days the campaign runs. Real calendar dates are chosen after approval.",)
    daily_start_time = models.TimeField(default=datetime.time(6, 0))
    daily_end_time = models.TimeField(default=datetime.time(22, 0))
    # Budget & pricing
    budget = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))],)
    estimated_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), validators=[MinValueValidator(Decimal('0.00'))], help_text="Calculated from billboard price_per_slot × slot count × campaign days.")
    actual_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))], default=Decimal('0.00'))
    admin_split_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), validators=[MinValueValidator(Decimal('0.00'))],)
    admanager_split_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), validators=[MinValueValidator(Decimal('0.00'))],)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)
    rejection_reason = models.TextField(blank=True)
    admin_reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_campaigns_admin")
    admin_reviewed_at = models.DateTimeField(null=True, blank=True)
    manager_reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_campaigns_manager") 
    manager_reviewed_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)          # starts the 7-day clock
    dates_confirmed_at = models.DateTimeField(null=True, blank=True)   # when advertiser picked dates
    
    @property
    def is_active(self):
        today = timezone.now().date()
        if not (self.start_date and self.end_date):
            return False
        return self.status == self.Status.ACTIVE and self.start_date <= today <= self.end_date
    
    def calculate_estimated_price(self):
        # Sum of (billboard.price_per_slot × slots_per_day × duration_days)
        if not self.pk:
            return 0
        total = 0
        for slot in self.campaign_slots.select_related("billboard").all():
            total += slot.billboard.price_per_slot * slot.slots_per_day * self.duration_days
        return total
    
    # Recalculates and updates the estimate field atomically.
    def sync_estimated_price(self):
        self.estimated_price = self.calculate_estimated_price()
        self.save(update_fields=["estimated_price"])

    def submit_for_approval(self):
        if self.status != self.Status.DRAFT:
            raise ValidationError("Only draft campaigns can be submitted.")
        if not self.campaign_slots.exists():
            raise ValidationError("Add at least one billboard before submitting.")
        if not self.advertiser.is_verified:
            raise ValidationError("Your advertiser account must be verified before submitting campaigns.")
        
        # Enforce budget bounds early
        self.estimated_price = self.calculate_estimated_price()
        if self.estimated_price > self.budget:
             raise ValidationError(f"Estimated price (₦{self.estimated_price}) exceeds your budget (₦{self.budget}).")
        self.status = self.Status.PENDING_ADMIN_REVIEW 
        self.save(update_fields=["status", "estimated_price", "updated_at"])

    # admins reviews dates/budget and forwards to ad manager. → pending_manager_review
    def admin_forward_to_manager(self, admin_user): 
        if self.status != self.Status.PENDING_ADMIN_REVIEW:
            raise ValidationError("Campaign must be in pending admin review.")
        self.status = self.Status.PENDING_MANAGER_REVIEW
        self.admin_reviewed_by = admin_user
        self.admin_reviewed_at = timezone.now()
        self.rejection_reason = ""
        self.save(update_fields=[
            "status", "admin_reviewed_by", "admin_reviewed_at",
            "rejection_reason", "updated_at",
        ])

    # Ad Manager approves, the campain approved (LIVE), media if fully approved.
    def manager_approve(self, manager_user):
        with transaction.atomic():
            # Lock the row and re-check status under the lock  but only to validate. All writes still happen on `self
            locked = type(self).objects.select_for_update().get(pk=self.pk)
            if locked.status != self.Status.PENDING_MANAGER_REVIEW:
                raise ValidationError("Campaign must be in pending manager review.")
            self.status = self.Status.APPROVED
            self.manager_reviewed_by = manager_user
            self.manager_reviewed_at = timezone.now()
            self.approved_at = timezone.now() # starts 7 days expiry count
            self.rejection_reason = ""
            
            # Calculate split prices based on current RevenueSetting
            from admin_panel.models import RevenueSetting
            setting, _ = RevenueSetting.objects.get_or_create(
                defaults={'admin_percentage': Decimal('30.00'), 'admanager_percentage': Decimal('70.00')}
            )
                
            self.actual_price = self.estimated_price
            self.admin_split_price = self.actual_price * (setting.admin_percentage / Decimal('100.00'))
            self.admanager_split_price = self.actual_price * (setting.admanager_percentage / Decimal('100.00'))
            
            self.save(update_fields=[
                "status", "manager_reviewed_by", "manager_reviewed_at", "approved_at",
                "rejection_reason", "actual_price", "admin_split_price", "admanager_split_price", "updated_at",
            ])
            # Fully approve the media at the same time
            self.media.fully_approve(manager_user)

    def reject(self, reviewer, reason=""):
        """
            admin or adManager
            Campaign → rejected. Media stays at its current stage.
        """
        if not reason.strip():
            raise ValidationError("A rejection reason is required.")
        if self.status not in [
            self.Status.PENDING_ADMIN_REVIEW,
            self.Status.PENDING_MANAGER_REVIEW,
        ]:
            raise ValidationError("Campaign cannot be rejected from its current status.")
 
        self.status = self.Status.REJECTED
        self.rejection_reason = reason
 
        if reviewer.is_staff:
            self.admin_reviewed_by = reviewer
            self.admin_reviewed_at = timezone.now()
            self.save(update_fields=[
                "status", "rejection_reason",
                "admin_reviewed_by", "admin_reviewed_at", "updated_at",
            ])
        else:
            self.manager_reviewed_by = reviewer
            self.manager_reviewed_at = timezone.now()
            self.save(update_fields=[
                "status", "rejection_reason",
                "manager_reviewed_by", "manager_reviewed_at", "updated_at",
            ])

    def cancel(self):
        allowed = [self.Status.DRAFT, self.Status.APPROVED, self.Status.ACTIVE]
        if self.status not in allowed:
            raise ValidationError("Campaign cannot be cancelled from its current status.")
        self.status = self.Status.CANCELLED
        self.save(update_fields=["status", "updated_at"])

    def confirm_dates(self, start_date, daily_start_time=None, daily_end_time=None):
        """
            Called when the advertiser picks a start date after approval —
            real per-day/per-hour availability is only knowable at this stage,
            so this is also the point where the advertiser may adjust their
            daypart if their original creation-time guess turns out to be
            unavailable. Ad manager approval is for the CONTENT and the
            BILLBOARD, not a specific locked time window, so revising the
            daypart here (before any TimeSlots exist) doesn't reopen anything
            that was actually approved.

            Actual TimeSlot generation + capacity check happens in the service
            layer (advertiser/services.py), wrapped in a transaction so a capacity
            failure rolls this back cleanly.
        """
        with transaction.atomic():
            locked = type(self).objects.select_for_update().get(pk=self.pk)
            if locked.status != self.Status.APPROVED:
                raise ValidationError("Campaign must be approved before selecting dates.")
            if start_date < timezone.now().date():
                raise ValidationError({"start_date": "Start date cannot be in the past."})

            from datetime import timedelta
            update_fields = ["start_date", "end_date", "dates_confirmed_at", "updated_at"]
           
            self.start_date = start_date
            self.end_date = start_date + timedelta(days=self.duration_days - 1)
            self.dates_confirmed_at = timezone.now()

            if daily_start_time is not None and daily_end_time is not None:
                if daily_start_time == daily_end_time:
                    raise ValidationError({ "daily_end_time": "Daily end time must be different from daily start time." })
                self.daily_start_time = daily_start_time
                self.daily_end_time = daily_end_time
                update_fields += ["daily_start_time", "daily_end_time"]

                # check that a campaign's daypart actually fits inside its billboard's operating hours
                for cs in self.campaign_slots.select_related("billboard").all():
                    cs.campaign = self
                    cs.full_clean()            
            self.save(update_fields=update_fields)

    def expire_approval(self):
        """Called by the daily expiry task for APPROVED campaigns with no
        confirmed dates after 7 days."""
        if self.status != self.Status.APPROVED or self.start_date:
            return  # dates already picked, or not in the right state — skip
        self.status = self.Status.APPROVAL_EXPIRED
        self.save(update_fields=["status", "updated_at"])

    def clean(self):
        super().clean()

        # Enforce strict media status constraints programmatically
        try:
            has_media = self.media is not None
        except ObjectDoesNotExist:
            has_media = False

        if has_media:
            approved_statuses = [
                Media.Status.ADMIN_APPROVED,
                Media.Status.FULLY_APPROVED,
            ]
            if self.media.status not in approved_statuses:
                raise ValidationError({
                    "media": "The chosen media file must be approved before scheduling campaigns."
                })
        
        if self.start_date and self.end_date:
            if self.end_date < self.start_date:
                raise ValidationError({"end_date": "End date cannot be before start date."})
            # Prevent booking past dates — applies to every DRAFT save, always.
            today = timezone.now().date()
            if self.status == self.Status.DRAFT and self.start_date < today:
                raise ValidationError({"start_date": "Start date cannot be in the past."})
    
        # Operations timeframe bounds
        if self.daily_start_time and self.daily_end_time:
            if isinstance(self.daily_start_time, datetime.time) and isinstance(self.daily_end_time, datetime.time):
                if self.daily_end_time == self.daily_start_time:
                    raise ValidationError({"daily_end_time": "Daily end time must be different from daily start time."})

    def save(self, *args, **kwargs):
        if not kwargs.get("update_fields"):
            self.full_clean()
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.name} [{self.status}]"

    class Meta:
        indexes = [
            models.Index(fields=["advertiser", "status"]),
            models.Index(fields=["status", "start_date", "end_date"]),
        ]

# connects an advertising Campaign to a specific Billboard.
class CampaignSlot(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey( Campaign, on_delete=models.CASCADE, related_name="campaign_slots")
    billboard = models.ForeignKey(Billboard, on_delete=models.PROTECT, related_name="campaign_slots")
    # number of times our ads get displayed
    slots_per_day = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(50)]) # store how many ads slot this campaign owns

    @property
    def slot_price(self):
        return ( self.billboard.price_per_slot * self.slots_per_day * self.campaign.duration_days)
    
    def clean(self):
        super().clean()
        if self.campaign_id and self.billboard_id:
            campaign_start = self.campaign.daily_start_time
            campaign_end = self.campaign.daily_end_time
            bb_start = self.billboard.operating_hours_start
            bb_end = self.billboard.operating_hours_end

            # A billboard's own operating_hours_start == operating_hours_end
            # means "open 24 hours" (unlike a campaign daypart, where equal
            # start/end is rejected as ambiguous — for a billboard's own
            # hours there's only one sensible reading). Any daypart fits.
            if bb_start != bb_end:
                def mins(t):
                    return t.hour * 60 + t.minute

                o_s, o_e = mins(bb_start), mins(bb_end)
                i_s, i_e = mins(campaign_start), mins(campaign_end)

                outer_len = (o_e - o_s) % 1440 or 1440
                inner_len = (i_e - i_s) % 1440 or 1440
                offset = (i_s - o_s) % 1440

                if offset + inner_len > outer_len:
                    raise ValidationError({
                        "billboard": (
                            f"'{self.billboard.name}' only operates "
                            f"{bb_start.strftime('%I:%M %p')}–{bb_end.strftime('%I:%M %p')}. "
                            f"Your campaign's daily window "
                            f"({campaign_start.strftime('%I:%M %p')}–{campaign_end.strftime('%I:%M %p')}) "
                            f"falls outside that range."
                        )
                    })

    class Meta:
        unique_together = [("campaign", "billboard")]
        indexes = [
            models.Index(fields=["campaign"]),
            models.Index(fields=["billboard"]),
        ]

    def save(self, *args, **kwargs):
        # Prevent slots modification if campaign is already locked for review/running
        if self.campaign.status not in [Campaign.Status.DRAFT, Campaign.Status.REJECTED]: 
            raise ValidationError("Cannot modify billboard slots on a locked or active campaign.")
        self.full_clean()
        super().save(*args, **kwargs)
        # Dynamic calculation engine hook: Auto-update campaign metadata metrics
        self.campaign.sync_estimated_price()

    def delete(self, *args, **kwargs):
        if self.campaign.status not in [Campaign.Status.DRAFT, Campaign.Status.REJECTED]:
            raise ValidationError("Cannot delete billboard slots from a locked or active campaign.")
        campaign_ref = self.campaign
        super().delete(*args, **kwargs)
        campaign_ref.sync_estimated_price()

    def __str__(self):
        return f"{self.campaign.name} → {self.billboard.name} ({self.slots_per_day}/day)"