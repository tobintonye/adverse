from rest_framework import serializers
from ..models import Device

class DeviceSerializer(serializers.ModelSerializer):
    is_online = serializers.BooleanField(read_only=True)

    class Meta:
        model = Device
        fields = (
            "id",
            "device_uid",
            "name",
            "location_name",
            "latitude",
            "longitude",
            "screen_width_px",
            "screen_height_px",
            "price_per_slot",
            "firmware_version",
            "is_online",
        )
        read_only_fields = ("id", "status", "last_seen_at", "is_online", "created_at")


class DeviceRegistrationSerializer(DeviceSerializer):
    auth_token = serializers.CharField(read_only=True)

    class Meta(DeviceSerializer.Meta):
        fields = DeviceSerializer.Meta.fields + ("auth_token",)

class DeviceUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Device
        fields = (
            "name",
            "location_name",
            "latitude",
            "longitude",
            "screen_width_px",
            "screen_height_px",
            "price_per_slot",
        )
        
class HeartbeatSerializer(serializers.Serializer):
    firmware_version = serializers.CharField(required=False, allow_blank=True, max_length=80)
    free_storage_mb = serializers.IntegerField(required=False, min_value=0)
    current_media_id = serializers.UUIDField(required=False)

class TokenRotateResponseSerializer(serializers.Serializer):
    # Write-only response — only returned once after rotation.
    new_auth_token = serializers.CharField()
    rotated_at = serializers.DateTimeField()