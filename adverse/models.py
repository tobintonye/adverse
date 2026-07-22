from django.db import models

class ContactMessage(models.Model):
    ROLE_CHOICES = [
        ('Advertiser', 'Advertiser'),
        ('Screen owner', 'Screen owner'),
        ('Partnership / Media', 'Partnership / Media'),
        ('Press', 'Press'),
        ('Other', 'Other'),
    ]

    name = models.CharField(max_length=150)
    email = models.EmailField()
    role = models.CharField(max_length=50, choices=ROLE_CHOICES, default='Advertiser')
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_processed = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.name} ({self.role}) - {self.email}"