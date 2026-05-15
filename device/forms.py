from django import forms
from .models import Device

# adManager register device form
class DeviceForm(forms.ModelForm):
    class Meta:
        model = Device
        fields = [
            'device_uid', 'name', 'location_name', 'price_per_slot' # setting simple for now 
        ]
        # widgets = {'address': forms.Textarea(attrs={'rows': 3}),}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Efficiently add Bootstrap classes to all whitelisted fields
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})