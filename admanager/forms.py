from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from .models import Admanager
from device.models import Billboard
import re

class AdManagerProfileForm(forms.ModelForm): 
    business_phone = forms.CharField(max_length=20, widget=forms.TextInput(attrs={'placeholder': 'e.g. 08012345678'}))
    
    class Meta: 
        model = Admanager
        fields = [
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
            'country'
        ]
        widgets = { 
            'address': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Full business address...'}),
            'business_name': forms.TextInput(attrs={'placeholder': 'e.g. Acme Media Group'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        business_type = cleaned_data.get("business_type")
        reg_number = cleaned_data.get("company_registration_number")

        #  If they choose 'Company', registration number should be required
        if business_type == Admanager.BusinessType.COMPANY and not reg_number: 
            self.add_error('company_registration_number', "Company registration is required for business accounts.")
        return cleaned_data
    
    def clean_business_phone(self):
        phone = self.cleaned_data.get('business_phone')
        # Remove any non-numeric characters except the '+'
        clean_phone = re.sub(r'[^\d+]', '', phone)
        if not re.match(r'^(\+234|0)[789][01]\d{8}$', clean_phone):
            raise ValidationError(
                "Phone number must be entered in the format: "
                "'08012345678' or '+2348012345678'."
            )
        return clean_phone


class BillboardForm(forms.ModelForm):
    latitude = forms.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=True,
        widget=forms.NumberInput(attrs={'placeholder': '6.4281', 'step': 'any'})
    )
    longitude = forms.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=True,
        widget=forms.NumberInput(attrs={'placeholder': '3.4219', 'step': 'any'})
    )
    price_per_slot = forms.DecimalField(min_value=0.01, widget=forms.NumberInput(attrs={'placeholder': '5000.00', 'step': '0.01'}))
    screen_width_px = forms.IntegerField(min_value=1, widget=forms.NumberInput(attrs={'placeholder': '1920'}))
    screen_height_px = forms.IntegerField(min_value=1, widget=forms.NumberInput(attrs={'placeholder': '1080'}))

    class Meta:
        model = Billboard
        fields = [
            'name', 'country', 'state', 'location_name', 'latitude', 'longitude',
            'screen_type', 'screen_width_px', 'screen_height_px',
            'charge_unit', 'price_per_slot', 'operating_hours_start', 'operating_hours_end',
            'availability', 'media_file',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Victoria Island Main Screen'}),
            'location_name': forms.TextInput(attrs={'placeholder': 'e.g. Adeola Odeku Street, VI, Lagos'}),
            'country': forms.TextInput(attrs={
                'placeholder': 'e.g. Nigeria',
                'class': 'input w-full',
                'id': 'country-input'
            }),
            'state': forms.TextInput(attrs={
                'placeholder': 'e.g. Lagos State',
                'class': 'input w-full',
                'id': 'state-input'
            }),
            'screen_width_px': forms.NumberInput(attrs={'placeholder': '1920'}),
            'screen_height_px': forms.NumberInput(attrs={'placeholder': '1080'}),
            'charge_unit': forms.Select(attrs={
                'class': 'select w-full',
                'id': 'charge-unit-select'
            }),
            'price_per_slot': forms.NumberInput(attrs={'placeholder': '5000.00', 'step': '0.01'}),
            'operating_hours_start': forms.TimeInput(attrs={'type': 'time'}),
            'operating_hours_end': forms.TimeInput(attrs={'type': 'time'}),
            'screen_type': forms.Select(attrs={
                'class': 'select w-full'
            }),
            'availability': forms.Select(attrs={
                'class': 'select w-full'
            }),
        }
