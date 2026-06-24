from rest_framework import serializers
 
from ..models import ( AdManagerEarning, AdManagerSubaccount, AdManagerSubaccountAuditLog, CampaignPayment, PayoutRecord)

class SubaccountSetupSerializer(serializers.Serializer):
    # Input for creating a Paystack subaccount during ad manager onboarding.
    bank_code = serializers.CharField(max_length=10)
    account_number = serializers.CharField(max_length=20)
    business_name = serializers.CharField(max_length=180)

    def validate_account_number(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("Account number must contain digits only.")
        if len(value) != 10: 
            raise serializers.ValidationError("Account number must be exactly 10 digits")
        return value
    
    def validate_bank_code(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("Bank code must contain digits only.")
        return value
    
class AdManagerSubaccountSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for returning subaccount details to the ad manager.
    - Never exposes the full account number (always masked).
    - subaccount_code is excluded; it is a Paystack-level identifier that
      should never be handed to client-facing responses. Use the admin
      serializer (AdminAdManagerSubaccountSerializer) for internal tooling.
    """
    account_number = serializers.CharField(ssource="masked_account_number", read_only=True)
    is_verified = serializers.BooleanField(read_only=True)

    class Meta:
        model = AdManagerSubaccount
        fields = ["id", "business_name", "bank_name", "account_number", "account_number", "is_active", "is_verified", "verified_at", "created_at"]
        read_only_fields = fields

class AdminAdManagerSubaccountSerializer(serializers.ModelSerializer):
    """
    Admin-only serializer. Includes subaccount_code for internal reconciliation.
    Never expose this to ad manager or advertiser-facing endpoints.
    """
    account_number = serializers.CharField(source="masked_account_number", read_only=True)

    is_verified = serializers.BooleanField(read_only=True)
    class Meta:
        model = AdManagerSubaccount
        fields = ["id", "subaccount_code", "business_name", "bank_name", "account_number", "account_number", "is_active", "is_verified", "verified_at", "created_at"]
        read_only_fields = fields

class UpdateBankDetailsSerializer(serializers.Serializer):
    # Input for updating an ad manager's bank details.
    bank_code = serializers.CharField(max_length=10)
    account_number = serializers.CharField(max_length=20)
    business_name = serializers.CharField(max_length=180, required=False)

    def validate_account_number(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("Account number must contain digits only.")
        
        if len(value) != 10:
            raise serializers.ValidationError("Account number must be exactly 10 digits.")
        return value
    
    def validate_bank_code(self, value): 
        if not value.isdigit():
            raise serializers.ValidationError("Bank code must contain digits only.")
        return value
    
class SubaccountAuditLogSerializer(serializers.ModelSerializer):
    """
    Admin-only. changed_by uses PrimaryKeyRelatedField to avoid leaking
    the user's __str__() representation (which may be an email or full name)
    into audit log responses. Use only on admin/internal endpoints.
    """
    changed_by = serializers.PrimaryKeyRelatedField(read_only=True)
 
    class Meta:
        model = AdManagerSubaccountAuditLog
        fields = ["id", "event", "changed_by", "note", "created_at"]
        read_only_fields = fields

# Campaign Payment
class InitiateCampaignPaymentSerializer(serializers.Serializer):
    # Input for initiating a campaign payment
    campaign_id = serializers.UUIDField()

class CampaignPaymentSerializer(serializers.ModelSerializer):
    """
    Client-facing payment serializer.
    - paystack_reference is excluded; it is an internal reconciliation field.
      Exposing it would let advertisers probe Paystack's Verify Transaction
      API directly. Use AdminCampaignPaymentSerializer for internal tooling.
    """
    campaign_name = serializers.CharField(source="campaign.name", read_only=True)

    class Meta:
        model = CampaignPayment
        fields = [ "id", "campaign", "campaign_name",  "total_amount",  "platform_fee",
                    "manager_amount",  "status", "reference",  "completed_at",  "refunded_at", "created_at"]
        
        read_only_fields = fields

class AdminCampaignPaymentSerializer(serializers.ModelSerializer):
    """
    Admin-only payment serializer. Includes paystack_reference for
    reconciliation. Never expose on advertiser or ad manager endpoints.
    """
    campaign_name = serializers.CharField(source="campaign.name", read_only=True)

    class Meta:
        models = CampaignPayment
        fields = ["id", "campaign", "campaign_name", "total_amount", "platform_fee",  "manager_amount","status",
                    "reference", "paystack_reference", "completed_at",  "refunded_at", "created_at", 
                ]
        read_only_fields = fields

# Ad Manager Earning
class AdManagerEarningSerializer(serializers.ModelSerializer):
    campaign_name = serializers.CharField(source="payment.campaign.name", read_only=True)

    class Meta:
         model = AdManagerEarning
         fields = [ "id", "campaign_name", "amount", "platform_fee", "paystack_reference", "earned_at"]
         read_only_fields = fields

# Payout Record
class PayoutRecordSerializer(serializers.ModelSerializer):
    """
    Ad-manager-facing payout history serializer.
    - account_number is always masked.
    - is_flagged is excluded; it is an internal compliance/risk field.
      Surfacing it to the ad manager would reveal that a payout is under
      review, which could prompt account manipulation before investigation.
      Use AdminPayoutRecordSerializer for internal tooling.
    """
    account_number = serializers.CharField(source="masked_account_number", read_only=True)
    class Meta:
        model = PayoutRecord
        fields = ["id", "amount", "bank_name", "account_number", "account_name", "status", "paystack_transfer_code", "completed_at", "created_at"]
        read_only_fields = fields

class AdminPayoutRecordSerializer(serializers.ModelSerializer):
    """
    Admin-only payout serializer. Includes is_flagged for compliance review.
    Never expose on ad manager or advertiser endpoints.
    """
    account_number = serializers.CharField(source="masked_account_number", read_only=True)

    class Meta:
        model = PayoutRecord
        fields = [ "id", "amount", "bank_name", "account_number", "account_name", "status", 
                    "paystack_transfer_code", "is_flagged", "completed_at", "created_at"
                  ]
        read_only_fields = fields

        
