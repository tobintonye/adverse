from rest_framework import serializers
from ..models import Billboard, PlayerDevice, PlaybackLog, DeviceMetric

class BillboardSerializer(serializers.ModelSerializer):
    resolution = serializers.CharField(read_only=True)
    is_paired = serializers.BooleanField(read_only=True)
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
            "is_paired",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "resolution", "is_paired", "created_at", "updated_at")


class BillboardWriteSerializer(serializers.ModelSerializer):
    # create and update — excludes computed/read-only fields
    class Meta:
        model = Billboard
        fields = (
            "name",
            "location_name",
            "latitude",
            "longitude",
            "screen_type",
            "screen_width_px",
            "screen_height_px",
            "price_per_slot",
            "operating_hours_start",
            "operating_hours_end",
            "availability",
        )
class PlayerDeviceSerializer(serializers.ModelSerializer):
    is_online = serializers.BooleanField(read_only=True)
    is_paired = serializers.BooleanField(read_only=True)
    billboard_name = serializers.CharField(source="billboard.name", read_only=True)
    class Meta:
        model = PlayerDevice
        fields = (
            "id",
            "device_uid",
            "pairing_code",
            "billboard",
            "billboard_name",
            "firmware_version",
            "status",
            "last_seen_at",
            "is_online",
            "is_paired",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "pairing_code",
            "auth_token",
            "status",
            "last_seen_at",
            "is_online",
            "is_paired",
            "billboard_name",
            "created_at",
            "updated_at",
    )

class PlayerDeviceRegistrationSerializer(PlayerDeviceSerializer):
    auth_token = serializers.CharField(read_only=True) # Returned once on registration — includes auth_token
    
    class Meta(PlayerDeviceSerializer.Meta):
        fields = PlayerDeviceSerializer.Meta.fields + ("auth_token",)

class PairDeviceSerializer(serializers.Serializer):
    """
    Ad manager submits the pairing code from the Android box
    and the billboard they want to assign it to.
    """
    pairing_code = serializers.CharField(max_length=12)
    billboard_id = serializers.UUIDField()

    def validate_pairing_code(self, value):
        try: 
            self._player = PlayerDevice.objects.get(pairing_code=value.upper())
        except PlayerDevice.DoesNotExist:
            raise serializers.ValidationError("Invalid pairing code.")
        if self._player.status == PlayerDevice.Status.DISABLED:
            raise serializers.ValidationError("This device has been disabled.")
        return value.upper()
    
    def validate_billboard_id(self, value):
        try:
            self._billboard = Billboard.objects.get(pk=value)
        except Billboard.DoesNotExist:
            raise serializers.ValidationError("Billboard not found.")
        return value
    
    def validate(self, attrs):
        # Prevent re-pairing a billboard that already has a live device
        billboard = getattr(self, "_billboard", None)
        if billboard and billboard.is_paired:
            existing = billboard.player_device
            if existing.status != PlayerDevice.Status.DISABLED:
                raise serializers.ValidationError(
                    "This billboard already has an active device paired. Disable it first."
                )
        return attrs
    
    def save(self, **kwargs):
        self._player.pair_to_billboard(self._billboard)
        return self._player
    
class HeartbeatSerializer(serializers.Serializer):
    firmware_version = serializers.CharField(required=False, allow_blank=True, max_length=80)
    free_storage_mb = serializers.IntegerField(required=False, min_value=0)
    current_media_id = serializers.UUIDField(required=False)

class PlaybackLogSerializer(serializers.ModelSerializer):
    class Meta:
        model  = PlaybackLog
        fields = ("id", "media_id", "started_at", "duration_seconds", "completed", "created_at")
        read_only_fields = ("id", "created_at")

class BulkPlaybackLogSerializer(serializers.Serializer):
    logs = PlaybackLogSerializer(many=True)

    def validate_logs(self, value):
        if not value:
            raise serializers.ValidationError("logs must not be empty.")
        if len(value) > 500:
            raise serializers.ValidationError("Maximum 500 logs per flush.")
        return value
    
class DeviceMetricSerializer(serializers.ModelSerializer):
    class Meta:
        model  = DeviceMetric
        fields = (
            "id", "cpu_usage_pct", "ram_usage_mb",
            "free_storage_mb", "temperature_celsius", "recorded_at",
        )
        read_only_fields = ("id", "recorded_at")