from rest_framework import serializers
from ..models import Advertiser, Media, Campaign, CampaignSlot
from device.models import Billboard
import magic
from django.db import transaction

# Advertiser Profile
class AdvertiserProfileSerializer(serializers.ModelSerializer):
    email = serializers.CharField(source="user.email", read_only=True)

    class Meta:
        model = Advertiser
        fields = (
            "id",
            "email",
            "first_name", 
            "last_name",
            "business_name",
            "business_category",
            "contact_phone",
            "website",
            "address",
            "is_verified",
            "verified_at",
            "created_at",
            "updated_at",
        )

        read_only_fields = ("id", "email", "is_verified", "verified_at", "created_at", "updated_at")

# Used for create and update of advertiser profile
class AdvertiserProfileWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Advertiser
        fields = (
            "business_name",
            "business_category",
            "first_name", 
            "last_name",
            "contact_phone",
            "website",
            "address",
        )

# Billboard — read only for advertisers (they browse, don't own)
class BillboardPublicSerializer(serializers.ModelSerializer):
    resolution = serializers.CharField(read_only=True)
    class Meta:
        model = Billboard
        fields = (
            "id",
            "name",
            "location_name",
            "latitude",
            "longitude",
            "screen_type",
            "screen_width_px",
            "screen_height_px",
            "resolution",
            "price_per_slot",
            "operating_hours_start",
            "operating_hours_end",
            "availability",
        )

# Media serializers 
ALLOWED_MIME_TYPES = {
    "image/jpeg", "image/png", "image/webp",
    "video/mp4", "video/quicktime", "video/webm",
}

IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
VIDEO_MIME_TYPES = {"video/mp4", "video/quicktime", "video/webm"}

MAX_IMAGE_BYTES = 10 * 1024 * 1024     # 10 MB
MAX_VIDEO_BYTES = 500 * 1024 * 1024    # 500 MB

# GET 
class MediaSerializer(serializers.ModelSerializer):
    file_url = serializers.CharField(read_only=True)
    file_size_mb = serializers.FloatField(read_only=True)
    reviewed_by_name = serializers.CharField(source="reviewed_by.get_full_name", read_only=True)

    class Meta:
        model = Media
        fields = (
            "id", "title", "file_url", "media_type", "duration_seconds",
            "file_size_bytes", "file_size_mb", "thumbnail", "status",
            "rejection_reason", "reviewed_by_name", "reviewed_at",
            "created_at", "updated_at",
        )

# POST -> validates file magic bytes and sets internal metadata.
class MediaUploadSerializer(serializers.ModelSerializer):
    file = serializers.FileField(required=True)

    class Meta:
        model = Media
        fields = ("title", "file", "duration_seconds")

    def validate_file(self, file):
        try: 
            header = file.read(2048)
            mime = magic.from_buffer(header, mime=True)
        finally:
            file.seek(0)
        if mime not in ALLOWED_MIME_TYPES:
            raise serializers.ValidationError(f"Unsupported format layout. Allowed: JPEG, PNG, WebP, MP4, MOV, WebM.")
        if mime in IMAGE_MIME_TYPES and file.size > MAX_IMAGE_BYTES:
            raise serializers.ValidationError("Image files cannot exceed 10 MB.")
        if mime in VIDEO_MIME_TYPES and file.size > MAX_VIDEO_BYTES:
            raise serializers.ValidationError("Video files cannot exceed 500 MB.")

        # Inject the verified type safely into serializer context dictionary
        self.context["detected_mime"] = mime
        return file

    def validate(self, attrs):
        if "file" not in attrs:
                return attrs
            
        mime = self.context.get("detected_mime")
        duration = attrs.get("duration_seconds")

        if mime in VIDEO_MIME_TYPES:
            if not duration:
                raise serializers.ValidationError({"duration_seconds": "Duration is required for video uploads."})
            attrs["media_type"] = Media.MediaType.VIDEO
        elif mime in IMAGE_MIME_TYPES:
            if duration:
                raise serializers.ValidationError({"duration_seconds": "Duration should not be set for image uploads."})
            attrs["media_type"] = Media.MediaType.IMAGE
            attrs["duration_seconds"] = None
        
        # Auto-fill tracked system fields before hitting the database creation stage
        attrs["file_size_bytes"] = attrs["file"].size
        attrs["advertiser"] = self.context["advertiser"]
        return attrs

    def create(self, validated_data):
        return super().create(validated_data)

class MediaReviewSerializer(serializers.Serializer):
    # Admin/ad manager action processor to approve or reject submissions.
    action = serializers.ChoiceField(choices=["approve", "reject"])
    rejection_reason = serializers.CharField(required=False, allow_blank=True, max_length=500)

    def validate(self, attrs):
        action = attrs.get("action")
        reason = attrs.get("rejection_reason", "").strip()
        
        if action == "reject" and not reason:
            raise serializers.ValidationError(
                {"rejection_reason": "A reason is required when rejecting media."}
            )
        return attrs

class CampaignSlotSerializer(serializers.ModelSerializer):
    billboard_name = serializers.CharField(source="billboard.name", read_only=True)
    billboard_location = serializers.CharField(source="billboard.location_name", read_only=True)
    slot_price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    
    class Meta: 
        model = CampaignSlot
        fields = (
            "id", "billboard", "billboard_name", "billboard_location",
            "slots_per_day", "slot_price",  
        )
        read_only_fields = ("id", "billboard_name", "billboard_location", "slot_price")

class CampaignSerializer(serializers.ModelSerializer):
    # GET - list pf campaign
    campaign_slots = CampaignSlotSerializer(many=True, read_only=True)
    media_title = serializers.CharField(source="media.title", read_only=True)
    media_type = serializers.CharField(source="media.media_type", read_only=True)
    duration_days = serializers.IntegerField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    reviewed_by_name = serializers.CharField(
        source="reviewed_by.get_full_name", read_only=True
    )
 
    class Meta:
        model = Campaign
        fields = (
            "id", "name", "media", "media_title", "media_type", "start_date",
            "end_date", "duration_days", "daily_start_time", "daily_end_time",
            "budget", "estimated_price", "status", "rejection_reason",
            "reviewed_by_name", "reviewed_at", "is_active", "campaign_slots",
            "created_at", "updated_at",
        )

# POST/ PUT/ PATCH
class CampaignWriteSerializer(serializers.ModelSerializer):
    slots = CampaignSlotSerializer(many=True, write_only=True, required=False)
    
    class Meta:
        model = Campaign
        fields = (
            "name", "media", "start_date", "end_date",
            "daily_start_time", "daily_end_time", "budget", "slots",
        )
    
    def validate_media(self, media): 
        if media.status != Media.Status.APPROVED:
            raise serializers.ValidationError("Only approved media files can be used to set up a campaign.")
        advertiser = self.context["advertiser"]
        if media.advertiser != advertiser:
            raise serializers.ValidationError("You do not own this media library asset.")
        return media
    
    def validate(self, attrs):
        startDate = attrs.get("start_date")
        endDate = attrs.get("end_date")
        if startDate and endDate and endDate < startDate:
             raise serializers.ValidationError({"end_date": "End date cannot be before start date."})
        daily_start = attrs.get("daily_start_time")
        daily_end = attrs.get("daily_end_time")
        if daily_start and daily_end and daily_end <= daily_start:
            raise serializers.ValidationError( {"daily_end_time": "Daily end time must be scheduled after start time."})
        return attrs
    
    def create(self, validated_data):
        slots_data = validated_data.pop("slots", [])
        advertiser = self.context["advertiser"]
        with transaction.atomic():
            campaign = Campaign.objects.create(advertiser=advertiser, **validated_data)

            for slot in slots_data:
                CampaignSlot.objects.create(
                    campaign=campaign,
                    billboard=slot["billboard"],
                    slot_per_day=slot.get("slots_per_day", 1), 
                )
            # Use the single automated sync helper from your model logic
            campaign.sync_estimated_price()
            return campaign
        
    def update(self, instance, validated_data):
        # SECURITY SECURE BOUND: Lock modifications if campaign isn't editable
        if instance.status not in [Campaign.Status.DRAFT, Campaign.Status.REJECTED]:
            raise serializers.ValidationError(f"Cannot modify this campaign because it is currently in '{instance.get_status_display()}' status.")

        slots_data = validated_data.pop("slots", None)

        with transaction.atomic():
            for attr, value, in validated_data.items():
                setattr(instance, attr, value)
            instance.save()

            if slots_data is not None:
                # Safely delete old records inside transaction
                instance.campaign_slots.all().delete()
                for slot in slots_data:
                    CampaignSlot.objects.create(
                        campaign=instance, 
                        billboard=slot["billboard"],
                        slots_per_day=slot.get("slots_per_day", 1),
                    )
            instance.sync_estimated_price()
            return instance
        
class CampaignPriceEstimateSerializer(serializers.Serializer):
    # Returns a live price estimate without saving anything.
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    slots = serializers.ListField(child=serializers.DateField(), min_length=1)

    def validate(self, attrs):
        attrs = super().validate(attrs)

        if attrs["end_date"] < attrs["start_date"]:
            raise serializers.ValidationError({
                "end_date": "End date cannot be before start date."
            })
        return attrs 

# Ad manager or admin approves / rejects a submitted campaign.
class CampaignReviewSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["approve", "reject"])
    rejection_reason = serializers.CharField(
        required=False, allow_blank=True, max_length=500
    )
 
    def validate(self, attrs):
        if attrs["action"] == "reject" and not attrs.get("rejection_reason", "").strip():
            raise serializers.ValidationError(
                {"rejection_reason": "A valid reason details breakdown is required when rejecting campaigns."}
            )
        return attrs