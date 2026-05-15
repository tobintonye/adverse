from rest_framework import serializers
import re
from django.core.validators import RegexValidator
from ..models import Admanager

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
        #  Remove spaces/dashes while keeping numbers and +
        cleaned_phone = re.sub(r'[^\d+]', '', value)
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