from django import forms
from django.core.exceptions import ValidationError
from device.models import Billboard

class BillboardForm(forms.ModelForm):
    """
    Used for both create and edit. Country/State are plain text inputs
    here — the template's JS (countriesnow.space + OSM autocomplete)
    populates them as <select> on the frontend, so Django just needs
    to accept whatever string value lands in request.POST.
    """

    class Meta:
        model = Billboard
        fields = [ 'name', 'country', 'state', 'location_name', 'latitude', 'longitude', 'media_file', 'screen_type',
                    'screen_width_px', 'screen_height_px', 'charge_unit', 'price_per_slot', 'operating_hours_start',
                    'operating_hours_end', 'availability',           
        ]

        widgets = {
            'name': forms.TextInput(attrs={ 'placeholder': 'e.g. Victoria Island Main Screen', 'class': 'input w-full'}),                
            'country': forms.TextInput(attrs={ 'class': 'select w-full', 'id': 'country-input'}),
            'state': forms.TextInput(attrs={'class': 'select w-full','id': 'state-input'}),
            'location_name': forms.TextInput(attrs={ 'placeholder': 'e.g. Adeola Odeku Street, VI, Lagos', 'class': 'input w-full', 'id': 'location-autocomplete', 'autocomplete': 'off'}),
            'latitude': forms.NumberInput(attrs={
                'placeholder': 'e.g. 6.4281',
                'step': 'any',
                'class': 'input w-full',
                'id': 'lat-input',
            }),
            'longitude': forms.NumberInput(attrs={
                'placeholder': 'e.g. 3.4219',
                'step': 'any',
                'class': 'input w-full',
                'id': 'lng-input',
            }),
            'screen_type': forms.Select(attrs={'class': 'select w-full'}),
            'screen_width_px': forms.NumberInput(attrs={
                'placeholder': '1920', 'class': 'input w-full',
            }),
            'screen_height_px': forms.NumberInput(attrs={
                'placeholder': '1080', 'class': 'input w-full',
            }),
            'charge_unit': forms.Select(attrs={
                'class': 'select w-full', 'id': 'charge-unit-select',
            }),
            'price_per_slot': forms.NumberInput(attrs={
                'placeholder': '5000.00', 'step': '0.01', 'class': 'input w-full',
            }),
            'operating_hours_start': forms.TimeInput(attrs={
                'type': 'time', 'class': 'input w-full',
            }),
            'operating_hours_end': forms.TimeInput(attrs={
                'type': 'time', 'class': 'input w-full',
            }),
            'availability': forms.Select(attrs={'class': 'select w-full'}),
            'media_file': forms.ClearableFileInput(attrs={
                'class': 'hidden', 'id': 'media-file-input',
                'accept': 'image/*,video/*',
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('operating_hours_start')
        end = cleaned_data.get('operating_hours_end')
        if start and end and start >= end:
            raise ValidationError("Operating hours start time must be before the end time.")
        return cleaned_data

    def clean_price_per_slot(self):
        price = self.cleaned_data.get('price_per_slot')
        if price is not None and price < 0:
            raise ValidationError("Price cannot be negative.")
        return price

    def clean_screen_width_px(self):
        width = self.cleaned_data.get('screen_width_px')
        if width is not None and width <= 0:
            raise ValidationError("Screen width must be greater than zero.")
        return width

    def clean_screen_height_px(self):
        height = self.cleaned_data.get('screen_height_px')
        if height is not None and height <= 0:
            raise ValidationError("Screen height must be greater than zero.")
        return height

    def clean_latitude(self):
        lat = self.cleaned_data.get('latitude')
        if lat is not None and not (-90 <= lat <= 90):
            raise ValidationError("Latitude must be between -90 and 90.")
        return lat

    def clean_longitude(self):
        lng = self.cleaned_data.get('longitude')
        if lng is not None and not (-180 <= lng <= 180):
            raise ValidationError("Longitude must be between -180 and 180.")
        return lng    