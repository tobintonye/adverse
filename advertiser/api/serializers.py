from rest_framework import serializers
from ..models import Advertiser
from device.models import Billboard
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