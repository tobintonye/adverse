from rest_framework import serializers
import re
from django.core.validators import RegexValidator
from ..models import Admanager
from advertiser.models import Campaign, CampaignSlot, Media


# Nigerian phone validation
phone_regex = RegexValidator(
    regex=r'^(\+234|0)[789][01]\d{8}$',
    message="Phone number must be entered in the format: '08012345678' or '+2348012345678'."
)

class AdManagerProfileSerializer(serializers.ModelSerializer): 
    business_phone = serializers.CharField(validators=[phone_regex], max_length=14)
    class Meta: 
        model = Admanager
        fields = [
            'id',
            'business_name',
            'business_type',
            'company_registration_number',
            'tax_identification_number',
            'business_email',
            'business_phone',
            'website',
            'address',
            'city',
            'state',
            'country',
        ]
        read_only_fields = ['id']
    
    def validate_business_phone(self, value):
        cleaned_phone = re.sub(r'[^\d+]', '', value)

        if not re.match(r'^(\+234|0)[789][01]\d{8}$', cleaned_phone):
            raise serializers.ValidationError("Invalid Nigerian phone number format.")
        return cleaned_phone
    
    def validate(self, attrs):
        business_type = attrs.get("business_type")
        reg_number = attrs.get("company_registration_number")
        # Require CAC registration for company accounts
        if business_type == Admanager.BusinessType.COMPANY and not reg_number:
            raise serializers.ValidationError({
                "company_registration_number":
                "Company registration number is required for company accounts."
            })
        return attrs

class AdManagerMediaDetailSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    class Meta:
        model = Media
        fields = ['id', 'title', 'media_type', 'file_url', 'thumbnail_url', 
                  'duration_seconds', 'status']

    def get_file_url(self, obj):
        request = self.context.get('request')
        if obj.file:
            return request.build_absolute_uri(obj.file.url) if request else obj.file.url
        return None
    
    def get_thumbnail_url(self, obj):
        request = self.context.get('request')
        if obj.thumbnail:
            return request.build_absolute_uri(obj.thumbnail.url) if request else obj.thumbnail.url
        return None
    
class CampaignSlotMinimalSerializer(serializers.ModelSerializer):
    # incoming requests to the Ad Manager with all relevant details (Advertiser profile, schedule, price, and active slots).
    billboard_name = serializers.CharField(source='billboard.name', read_only=True)

    class Meta:
         model = CampaignSlot
         fields = ['id', 'billboard', 'billboard_name', 'slots_per_day', 'slot_price']

class AdManagerCampaignRequestSerializer(serializers.ModelSerializer):
    advertiser_business_name = serializers.CharField(source='advertiser.business_name', read_only=True)
    slots = CampaignSlotMinimalSerializer(source='campaign_slots', many=True, read_only=True)
    duration_days = serializers.IntegerField(read_only=True)
    media = AdManagerMediaDetailSerializer(read_only=True)

    class Meta:
        model = Campaign
        fields = [
            'id', 'name', 'advertiser', 'advertiser_business_name', 'media', # display the url instead of the id
            'start_date', 'end_date', 'daily_start_time', 'daily_end_time',
            'estimated_price', 'status', 'rejection_reason', 'duration_days', 'slots'
        ]