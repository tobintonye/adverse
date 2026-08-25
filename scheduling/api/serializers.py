from rest_framework import serializers
from ..models import TimeSlot, BillboardCapacity, ScheduleGenerationLog

class TimeSlotSerializer(serializers.ModelSerializer):
    campaign_name = serializers.CharField(source="campaign.name", read_only=True)
    media_title = serializers.CharField(source="campaign.media.title", read_only=True)
    media_url = serializers.SerializerMethodField()
    content_hash = serializers.CharField(source="campaign.media.file_hash", read_only=True)
    advertiser = serializers.CharField(source="campaign.advertiser.business_name", read_only=True)

    def get_media_url(self, obj):
        relative_url = obj.campaign.media.playback_url
        if not relative_url:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(relative_url) if request else relative_url

    class Meta: 
        model = TimeSlot
        fields = ("id", "date", "scheduled_time", "play_order", "duration_seconds", "campaign_name", "media_title", "media_url", "content_hash", "advertiser", "is_active",)

class BillboardCapacitySerializer(serializers.ModelSerializer):
    billboard_name = serializers.CharField(source="billboard.name", read_only=True)

    class Meta:
        model = BillboardCapacity
        fields = ("id", "billboard_name", "max_slots_per_day", "slot_duration_seconds", "last_calculated_at",)


class ScheduleGenerationLogSerializer(serializers.ModelSerializer):
    campaign_name = serializers.CharField(source="campaign.name", read_only=True)

    class Meta: 
        model = ScheduleGenerationLog
        fields = ("id", "campaign_name","result", "slots_created", "slots_skipped", "error_message", "generated_at",)


class CapacityCheckSerializer(serializers.Serializer):
    """Used by the estimate endpoint before booking."""
    billboard_id  = serializers.UUIDField()
    start_date    = serializers.DateField()
    end_date      = serializers.DateField()
    slots_per_day = serializers.IntegerField(min_value=1)
 
    def validate(self, attrs):
        if attrs["end_date"] < attrs["start_date"]:
            raise serializers.ValidationError(
                {"end_date": "End date cannot be before start date."}
            )
        return attrs
 
