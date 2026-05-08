from django.db import models
from admanager.models import Admanager
import uuid

class Device(models.Model): 
    STATUS_CHOICES = (
        ('online', 'Online'),
        ('offline', 'Offline'),
        ('maintenance', 'Maintenance'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device_owner = models.ForeignKey(Admanager, on_delete=models.CASCADE)
    device_id = models.CharField(max_length=255, unique=True, db_index=True) 
    name = models.CharField(max_length=255)
    location_name = models.CharField(max_length=255)    
    address = models.TextField()
    screen_resolution = models.CharField(max_length=50, default='1920x1080')
    screen_size = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='offline')
  
    # Device specs
    android_version = models.CharField(max_length=50, blank=True)
    device_model = models.CharField(max_length=100, blank=True)
    storage_capacity = models.BigIntegerField(default=0)
    storage_available = models.BigIntegerField(default=0)
    
    price_per_slot = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='NGN')
    
    #status tracking
    last_sync = models.DateTimeField(null=True, blank=True)
    last_heartbeat = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'devices'
        indexes = [
            models.Index(fields=['device_id']),
            models.Index(fields=['status'])
        ]
    def __str__(self):
        return f"{self.name} - {self.location_name}"