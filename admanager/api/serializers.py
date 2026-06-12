from rest_framework import serializers
import re
import requests
from django.conf import settings
from django.core.validators import RegexValidator
from ..models import Admanager
from advertiser.models import Campaign, CampaignSlot, Media
from decimal import Decimal

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
            "total_billboards", "total_campaigns_serverd", "total_impressions",
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

class AdManagerBankAccountSerializer(serializers.ModelSerializer):
    """
    Manage bank account details for payouts.
    Separate from profile — sensitive fields kept isolated.
    """

    class Meta:
        model = Admanager
        fields = ["bank_name", "account_number", "account_name", "bank_code", "recipient_code"]
        read_only_fields = ["recipient_code"]

    def validate(self, data):
        account_number = data.get("account_number")
        bank_code = data.get("bank_code")

        cleaned_account = re.sub(r'\D', '', account_number)
        if len(cleaned_account) != 10:
            raise serializers.ValidationError(
                {"account_number": "Nigerian account numbers must be exactly 10 digits."}
            )
        data["account_number"] = cleaned_account
        # Live verification with Paystack API to prevent fraudulent or broken inputs
        url = f"https://paystack.co{cleaned_account}&bank_code={bank_code}"
        headers = {
            "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"
        }
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response_data = response.json()
            if response.status_code != 200 or not response_data.get("status"):
                raise serializers.ValidationError(
                    {"account_number": "Could not verify this bank account with Paystack."}
                )
            # Update the account name with the official name from the bank
            data["account_name"] = response_data["data"]["account_name"]
        except requests.exceptions.RequestException:
            raise serializers.ValidationError(
                {"detail": "Bank verification service is temporarily down. Try again later."}
            )
        return data
    def update(self, instance, validated_data):
        # Automatically generate a Paystack Transfer Recipient code before saving.
        # Create a recipient on Paystack to pay them securely later
        url = "https://paystack.co"
        headers = {
            "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "type": "nuban",
            "name": validated_data["account_name"],
            "account_number": validated_data["account_number"],
            "bank_code": validated_data["bank_code"],
            "currency": "NGN"
        }
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            res_json = response.json()
            if response.status_code == 201 and res_json.get("status"):
                # Save the secure recipient code to database
                validated_data["recipient_code"] = res_json["data"]["recipient_code"]
            else:
                raise serializers.ValidationError("Failed to register payout account with payment provider.")
                
        except requests.exceptions.RequestException:
            raise serializers.ValidationError("Payment network error. Please try again.")
        return super().update(instance, validated_data)
    
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
    
class AdManagerDashboardSerializer(serializers.ModelSerializer):
    pending_campaigns = serializers.IntegerField(read_only=True)
    active_campaigns = serializers.IntegerField(read_only=True)
    total_earnings = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    wallet_balance = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    
    is_verified = serializers.BooleanField(read_only=True)
    has_bank_account = serializers.BooleanField(read_only=True)
 
    class Meta:
        model = Admanager
        fields = [
            "id", "business_name", "verification_status", "is_verified",
            "has_bank_account", "commission_rate",
            "total_billboards", "total_campaigns_served", "total_impressions",
            "pending_campaigns", "active_campaigns",
            "total_earnings", "wallet_balance",
        ]
    
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
 