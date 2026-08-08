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
    # full profile detail including verification status and stats.
    username = serializers.CharField(source="user.username",read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)
    is_verified = serializers.BooleanField(read_only=True)
    has_bank_account = serializers.BooleanField(read_only=True)
    pending_campaigns = serializers.SerializerMethodField()
 
    class Meta:
        model  = Admanager
        fields = [
            "id", "username", "email",
            "business_name", "business_type",
            "company_registration_number", "tax_identification_number",
            "business_email", "business_phone",
            "website",
            "address", "city", "state", "country",
            "verification_status", "is_verified", "is_active",
            "rejection_reason", "suspension_reason",
            "verified_at",
            "commission_rate", "has_bank_account",
            "total_billboards", "total_impressions",
            "pending_campaigns",
            "created_at", "updated_at",
        ]
        read_only_fields = fields   
 
    def get_pending_campaigns(self, obj):
       # How many campaigns are currently waiting for this manager's approval.
        return obj.pending_review_campaigns.count()

class AdManagerProfileWriteSerializer(serializers.ModelSerializer): 
    business_phone = serializers.CharField(validators=[phone_regex], max_length=14)
    class Meta: 
        model = Admanager
        fields = [
            "business_name", "business_type",
            "company_registration_number", "tax_identification_number",
            "business_email", "business_phone",
            "website",
            "address", "city", "state", "country",
        ]
        read_only_fields = ['id']
    
    def validate_business_phone(self, value):
        cleaned_phone = re.sub(r'[^\d+]', '', value)
        if not re.match(r'^(\+234|0)[789][01]\d{8}$', cleaned_phone):
            raise serializers.ValidationError("Invalid Nigerian phone number format.")
        return cleaned_phone
    
    def validate(self, attrs):
        business_type = attrs.get("business_type", self.instance.business_type if self.instance else None)
        reg_number = attrs.get("company_registration_number")
        # Require CAC registration for company accounts
        if business_type == Admanager.BusinessType.COMPANY and not reg_number:
            raise serializers.ValidationError({
                "company_registration_number":
                "Company registration number is required for company accounts."
            })
        return attrs
    
class AdManagerVerificationSerializer(serializers.Serializer):
    # Admin-only — approve, reject, suspend or reinstate an ad manager account
    action = serializers.ChoiceField(choices=["verify", "reject", "suspend", "reinstate"])
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)
 
    def validate(self, attrs):
        action = attrs["action"]
        reason = attrs.get("reason", "").strip()
        if action in ["reject", "suspend"] and not reason:
            raise serializers.ValidationError(
                {"reason": f"A reason is required when performing '{action}'."}
            )
        return attrs
    
class AdManagerDashboardSerializer(serializers.Serializer):
    """
    Plain Serializer, not ModelSerializer — the dashboard view now builds a
    dict from live, correctly-computed values (matching the web dashboard's
    approach) rather than relying on ORM annotate() over @property fields,
    which cannot work (see AdManagerDashboardView fix).
    """
    id = serializers.UUIDField(read_only=True)
    business_name = serializers.CharField(read_only=True)
    verification_status = serializers.CharField(read_only=True)
    is_verified = serializers.BooleanField(read_only=True)
    has_bank_account = serializers.BooleanField(read_only=True)
    commission_rate = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    total_billboards = serializers.IntegerField(read_only=True)
    total_campaigns_served = serializers.IntegerField(read_only=True)
    total_impressions = serializers.IntegerField(read_only=True)
    pending_campaigns = serializers.IntegerField(read_only=True)
    active_campaigns = serializers.IntegerField(read_only=True)
    total_earnings = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    available_balance = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

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
    admin_reviewed_by_name = serializers.CharField(source="admin_reviewed_by.get_full_name", read_only=True)
    class Meta:
        model = Campaign
        fields = [
            'id', 'name', 'advertiser', 'advertiser_business_name', 'media', # display the url instead of the id
            'start_date', 'end_date', 'daily_start_time', 'daily_end_time',
            'estimated_price', 'status', 'rejection_reason', 'duration_days', 'slots', "admin_reviewed_by_name", "admin_reviewed_at",
        ]

class AdManagerCampaignReviewSerializer(serializers.Serializer):
    # Ad manager approves or rejects a campaign in PENDING_MANAGER_REVIEW
    action = serializers.ChoiceField(choices=["approve", "reject"])
    rejection_reason = serializers.CharField(required=False, allow_blank=True, max_length=500)
 
    def validate(self, attrs):
        if attrs["action"] == "reject" and not attrs.get("rejection_reason", "").strip():
            raise serializers.ValidationError(
                {"rejection_reason": "A detailed rejection reason is required."}
            )
        return attrs