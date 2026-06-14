from django import forms
from .models import Advertiser, Media, Campaign, CampaignSlot
from device.models import Billboard


class AdvertiserProfileForm(forms.ModelForm):
    class Meta:
        model = Advertiser
        fields = ['first_name', 'last_name', 'business_name', 'business_category', 'contact_phone', 'website', 'address']
        widgets = {
            'first_name': forms.TextInput(attrs={'placeholder': 'Jane'}),
            'last_name': forms.TextInput(attrs={'placeholder': 'Doe'}),
            'business_name': forms.TextInput(attrs={'placeholder': 'e.g. Bright Sparks Ltd'}),
            'contact_phone': forms.TextInput(attrs={'placeholder': '08012345678'}),
            'website': forms.URLInput(attrs={'placeholder': 'https://yoursite.com'}),
            'address': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Business address...'}),
        }


class MediaUploadForm(forms.ModelForm):
    class Meta:
        model = Media
        fields = ['title', 'file', 'media_type', 'duration_seconds', 'thumbnail']
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'e.g. Christmas Promo 2026'}),
            'duration_seconds': forms.NumberInput(attrs={'placeholder': '30', 'min': '1'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        media_type = cleaned_data.get('media_type')
        duration = cleaned_data.get('duration_seconds')
        if media_type == Media.MediaType.VIDEO and not duration:
            self.add_error('duration_seconds', 'Duration is required for video media.')
        if media_type == Media.MediaType.IMAGE and duration:
            self.add_error('duration_seconds', 'Images cannot have a playing duration.')
        return cleaned_data


class CampaignForm(forms.ModelForm):
    billboard = forms.ModelChoiceField(
        queryset=Billboard.objects.filter(availability='available'),
        widget=forms.Select,
        required=True,
        label='Select Billboard',
        empty_label='Choose a billboard...',
    )
    slots_per_day = forms.IntegerField(min_value=1, initial=1, label='Quantity (slots/hours/days)')

    class Meta:
        model = Campaign
        fields = ['name', 'media', 'start_date', 'end_date', 'budget']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Ramadan Campaign 2026'}),
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'budget': forms.NumberInput(attrs={'placeholder': '500000.00', 'step': '0.01'}),
        }

    def __init__(self, *args, advertiser=None, **kwargs):
        super().__init__(*args, **kwargs)
        if advertiser:
            self.fields['media'].queryset = Media.objects.filter(
                advertiser=advertiser,
                status__in=[
                    Media.Status.ADMIN_APPROVED,
                    Media.Status.FULLY_APPROVED,
                ],
            ).order_by('-created_at')
        self.fields['media'].empty_label = 'Select your approved media...'
