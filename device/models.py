import secrets

from django.db import models
from django.utils import timezone

from admanager.models import Admanager
from common.models import TimeStampedModel

class Device(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        OFFLINE = "offline", "Offline"
        DISABLED = "disabled", "Disabled"

    ad_manager = models.ForeignKey(Admanager, on_delete=models.CASCADE, related_name="devices")
    device_uid = models.CharField(max_length=80, unique=True) # billboard/device identifier
    auth_token = models.CharField(max_length=96, unique=True, editable=False) 
    name = models.CharField(max_length=120)
    location_name = models.CharField(max_length=255)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    screen_width_px = models.PositiveIntegerField(default=1920)
    screen_height_px = models.PositiveIntegerField(default=1080)
    price_per_slot= models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    firmware_version = models.CharField(max_length=80, blank=True)

    def save(self, *args, **kwargs):
        if not self.auth_token:
            self.auth_token = secrets.token_urlsafe(48)
            if "update_fields" in kwargs and kwargs["update_fields"] is not None:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {"auth_token"}
        super().save(*args, **kwargs)
    
    # to be removed in prod
    @property
    def is_authenticated(self):
        return True
    
    @property
    def is_online(self):
        if not self.last_seen_at:
            return False
        return self.last_seen_at >= timezone.now() - timezone.timedelta(minutes=5)

    # andriod app to ping this endpoint for status update
    def mark_heartbeat(self, firmware_version="", free_storage_mb=None, current_media_id=None):
        self.last_seen_at = timezone.now()
        self.status = self.Status.ACTIVE
        update_fields = ["last_seen_at", "status", "updated_at"]

        if firmware_version:
            self.firmware_version = firmware_version
            update_fields.append("firmware_version")

        self.save(update_fields=update_fields)

    # if device token gets leak
    def rotate_token(self): 
        self.auth_token = secrets.token_urlsafe(48)
        self.save(update_fields=["auth_token", "updated_at"])

    def __str__(self):
        return f"{self.name} ({self.device_uid})"
    
    class Meta:
        indexes = [
            models.Index(fields=["device_uid"]),
            models.Index(fields=["status"]),
            models.Index(fields=["last_seen_at"]),
        ]