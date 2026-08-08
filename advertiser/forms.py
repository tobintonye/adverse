import hashlib
import magic
from django import forms
from .models import Advertiser, Media, Campaign, CampaignSlot
from device.models import Billboard
from django.core.exceptions import ValidationError
import re

#  MIME type constants
ALLOWED_MIME_TYPES = {
    "image/jpeg", "image/png", "image/webp",
    "video/mp4", "video/quicktime", "video/webm",
}

IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
VIDEO_MIME_TYPES = {"video/mp4", "video/quicktime", "video/webm"}

MAX_IMAGE_BYTES = 10 * 1024 * 1024     # 10 MB
MAX_VIDEO_BYTES = 500 * 1024 * 1024    # 500 MB

class AdvertiserProfileForm(forms.ModelForm):
    class Meta:
        model = Advertiser
        fields = ['first_name', 'last_name', 'business_name', 'business_category', 'contact_phone', 'website', 'address']
        widgets = {
            'first_name': forms.TextInput(attrs={'placeholder': 'Jane'}),
            'last_name': forms.TextInput(attrs={'placeholder': 'Doe'}),
            'business_name': forms.TextInput(attrs={'placeholder': 'e.g. Bright Sparks Ltd'}),
            'contact_phone': forms.TextInput(attrs={'placeholder': '08012345678'}),
            'website': forms.URLInput(attrs={'placeholder': 'https://yourbusiness.com'}),
            'address': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Business address...'}),
        }
    def clean_contact_phone(self):
        phone = self.cleaned_data.get("contact_phone", "").strip()
        if not phone:
            return phone
        cleaned = re.sub(r"[^\d+]", "", phone)
        if not re.match(r"^(\+234|0)[789][01]\d{8}$", cleaned):
            raise ValidationError(
                "Phone number must be in the format '08012345678' or '+2348012345678'."
            )
        return cleaned

class MediaUploadForm(forms.ModelForm):
    class Meta:
        model = Media
        fields = ['title', 'file', 'duration_seconds', 'thumbnail']
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'e.g. Summer Sale Banner'}),
            'duration_seconds': forms.NumberInput(attrs={'placeholder': 'Required for video, e.g. 15', 'min': '1'}),
        }

    def validate_unique(self):
        pass
    
    def clean_file(self):
        file = self.cleaned_data.get("file")
        if not file:
            return file
        
        # Magic-byte MIME detection
        try: 
            header = file.read(2048)
            detected_mime = magic.from_buffer(header, mime=True)
        finally:
            file.seek(0)

        if detected_mime not in ALLOWED_MIME_TYPES:
            raise ValidationError(
                f"Unsupported file format (detected: {detected_mime}). "
                f"Allowed formats: JPEG, PNG, WebP, MP4, MOV, WebM."
            )
        
        # Size enforcement at byte level
        if detected_mime in IMAGE_MIME_TYPES and file.size > MAX_IMAGE_BYTES:
            raise ValidationError(
                f"Image files cannot exceed {MAX_IMAGE_BYTES // (1024 * 1024)} MB. "
                f"Your file is {file.size / (1024 * 1024):.1f} MB."
            )
        if detected_mime in VIDEO_MIME_TYPES and file.size > MAX_VIDEO_BYTES:
            raise ValidationError(
                f"Video files cannot exceed {MAX_VIDEO_BYTES // (1024 * 1024)} MB. "
                f"Your file is {file.size / (1024 * 1024):.1f} MB."
            )

        self._detected_mime = detected_mime
        return file
    
    def clean(self):
        cleaned_data = super().clean()
        file = cleaned_data.get("file")
        duration_seconds = cleaned_data.get("duration_seconds")

        # Only continue if clean_file() succeeded (mime is available)
        detected_mime = getattr(self, "_detected_mime", None)
        if not file or not detected_mime:
            return cleaned_data
        
        # Auto-set media_type from detected MIME 
        if detected_mime in IMAGE_MIME_TYPES:
            cleaned_data["media_type"] = Media.MediaType.IMAGE
            if duration_seconds is not None:
                self.add_error(
                    "duration_seconds",
                    "Duration should not be set for image uploads.",
                )
            cleaned_data["duration_seconds"] = None
 
        elif detected_mime in VIDEO_MIME_TYPES:
            cleaned_data["media_type"] = Media.MediaType.VIDEO
            if not duration_seconds:
                self.add_error("duration_seconds", "Duration is required for video uploads.",)
 
        # Pre-compute file_size_bytes (avoids a second .size call in
        # Media.clean() and keeps the model's full_clean consistent) 
        cleaned_data["file_size_bytes"] = file.size
        return cleaned_data
 
    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.media_type = self.cleaned_data["media_type"]
        instance.file_size_bytes = self.cleaned_data.get("file_size_bytes", 0)
        if commit:
            instance.save()
        return instance
    
class CampaignForm(forms.ModelForm):
    """
    Mirrors CampaignWriteSerializer's validate() rules.
    Media choices are scoped to this advertiser's ADMIN_APPROVED files only.

    NOTE: start_date/end_date are NOT collected here anymore. The advertiser
    only picks duration_days at creation time actual calendar dates are
    chosen after approval via the campaign_select_dates view. This prevents
    dates going stale while the campaign sits in review.
    """
    daily_start_time = forms.TimeField(
        input_formats=["%H:%M", "%H:%M:%S"],
        widget=forms.TimeInput(attrs={"type": "time"}),
    )
    daily_end_time = forms.TimeField(
        input_formats=["%H:%M", "%H:%M:%S"],
        widget=forms.TimeInput(attrs={"type": "time"}),
    )
    
    def __init__(self, advertiser, *args, **kwargs):
        self.advertiser = advertiser
        super().__init__(*args, **kwargs)
        # Scope media dropdown to this advertiser's admin-approved files only
        self.fields["media"].queryset = Media.objects.filter(
            advertiser=advertiser,
            status=Media.Status.ADMIN_APPROVED,
        )
        self.fields["media"].empty_label = "Select approved media..."

    class Meta:
        model = Campaign
        fields = ['name', 'media', 'duration_days', 'budget', 'daily_start_time', 'daily_end_time']
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. Eid Sale 2026"}),
            "duration_days": forms.NumberInput(attrs={"min": 1, "max": 365, "placeholder": "e.g. 7"}),
           
            "budget": forms.NumberInput(attrs={"placeholder": "e.g. 150000", "min": "0"}),
        }
    
    def clean_media(self):
        media = self.cleaned_data.get("media")
        if not media:
            return media
        if media.status != Media.Status.ADMIN_APPROVED: 
            raise ValidationError("Only admin-approved media files can be used in a campaign.")
        if media.advertiser != self.advertiser:
            raise ValidationError("You do not own this media asset.")
        return media
    
    def clean_duration_days(self):
        duration = self.cleaned_data.get("duration_days")
        if duration is not None and duration < 1:
            raise ValidationError("Campaign must run for at least 1 day.")
        return duration
    
    def clean_name(self): 
        name = self.cleaned_data.get("name", "").strip()
        locked_statuses = [
            Campaign.Status.DRAFT,
            Campaign.Status.PENDING_ADMIN_REVIEW,
            Campaign.Status.PENDING_MANAGER_REVIEW,
            Campaign.Status.APPROVED,
            Campaign.Status.ACTIVE,
        ]
        qs = Campaign.objects.filter(advertiser=self.advertiser, name__iexact=name, status__in=locked_statuses)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(f"You already have an active or draft campaign named '{name}'.")
        return name
    
    def clean(self):
        cleaned_data = super().clean()
        daily_start = cleaned_data.get("daily_start_time")
        daily_end = cleaned_data.get("daily_end_time")
        if daily_start and daily_end and daily_end <= daily_start:
            self.add_error("daily_end_time", "Daily end time must be after daily start time.")
        return cleaned_data

class CampaignSlotForm(forms.ModelForm):
    """
    Used inline when building a campaign — lets the advertiser pick a
    billboard and how many slots per day to book on it.
    Mirrors CampaignSlotSerializer's field structure.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show available billboards in the dropdown
        self.fields["billboard"].queryset = Billboard.objects.filter(
            availability=Billboard.Availability.AVAILABLE
        ).select_related("ad_manager")
        self.fields["billboard"].empty_label = "Select a billboard..."
 
    class Meta:
        model = CampaignSlot
        fields = ["billboard", "slots_per_day"]
        widgets = {
            "slots_per_day": forms.NumberInput(attrs={"min": 1, "value": 1}),
        }