from rest_framework import serializers
from ..models import Advertiser, Media
from device.models import Billboard
import magic

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