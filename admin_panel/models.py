from django.db import models
from decimal import Decimal
from django.core.exceptions import ValidationError

class RevenueSetting(models.Model):
    admin_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('30.00'))
    admanager_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('70.00'))
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        if self.admin_percentage + self.admanager_percentage != Decimal('100.00'):
            raise ValidationError("The sum of Admin and AdManager percentages must equal 100%.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Admin: {self.admin_percentage}%, AdManager: {self.admanager_percentage}%"
