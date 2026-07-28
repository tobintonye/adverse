import random
import secrets
import string
import uuid

from django.db import models
from django.utils import timezone

from admanager.models import Admanager
from common.models import TimeStampedModel

# Billboard
# Business registration of a screen. Exists independently of any hardware.
# Ad managers create these first; hardware pairs to them later
class Billboard(TimeStampedModel):
    class ScreenType(models.TextChoices): 
        LED = "led", "LED"
        LCD = "lcd", "LCD"
        DIGITAL = "digital", "Digital"

    class Availability(models.TextChoices): 
        AVAILABLE = "available", "Available"
        UNAVAILABLE = "unavailable", "Unavailable"
        MAINTENANCE = "maintenance", "Under Maintenance"

    class ChargeUnit(models.TextChoices):
        HOURLY = "hourly", "Hourly"
        DAILY = "daily", "Daily"
        SLOT = "slot", "Per Slot"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ad_manager = models.ForeignKey(Admanager, on_delete=models.CASCADE, related_name="billboards")
    name = models.CharField(max_length=120)
    location_name = models.CharField(max_length=255)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    country = models.CharField(max_length=100, default="Nigeria", blank=True)
    state = models.CharField(max_length=100, blank=True)
    media_file = models.FileField(upload_to="billboards/media/", null=True, blank=True, help_text="Upload an image or video representing this billboard's physical state.")

    # Screen specs
    screen_type = models.CharField(max_length=24, choices=ScreenType.choices, default=ScreenType.LED)
    screen_width_px = models.PositiveIntegerField(default=1920)
    screen_height_px = models.PositiveIntegerField(default=1080)
    
    # Business
    price_per_slot = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    charge_unit = models.CharField(max_length=10, choices=ChargeUnit.choices, default=ChargeUnit.SLOT)
    operating_hours_start = models.TimeField(default="06:00")
    operating_hours_end = models.TimeField(default="22:00")
    
    # Status — independent of whether a device is paired or online
    availability = models.CharField( max_length=24, choices=Availability.choices, default=Availability.AVAILABLE)

    # True if an active PlayerDevice is assigned to this billboard.
    @property
    def is_paired(self):
        return hasattr(self, "player_device") and self.player_device is not None
    
    @property
    def resolution(self):
        return f"{self.screen_width_px}x{self.screen_height_px}"
    
    def __str__(self):
        return f"{self.name} — {self.location_name}"
    
    class Meta:
        indexes = [
            models.Index(fields=["ad_manager"]),
            models.Index(fields=["availability"]),
        ]

# The physical Android box that pairs to a Billboard and authenticates via token.
# Separated so swapping hardware never loses billboard/campaign data.
class PlayerDevice(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        OFFLINE = "offline", "Offline"
        DISABLED = "disabled", "Disabled"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    billboard = models.OneToOneField(Billboard, on_delete=models.SET_NULL, null=True, blank=True, related_name="player_device")
    pairing_code = models.CharField(max_length=12, unique=True, blank=True) 
    auth_token = models.CharField(max_length=96, unique=True, editable=False) 
    device_uid = models.CharField(max_length=80, unique=True) # device_uid is hardware-sourced (IMEI, MAC, serial), not guessable like a sequential ID
    firmware_version = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    # Set once when the box first claims its auth_token
    token_claimed_at = models.DateTimeField(null=True, blank=True)
    
    # to be removed in prod
    @property
    def is_authenticated(self):
        return True
    
    @property
    def is_online(self):
        if not self.last_seen_at:
            return False
        return self.last_seen_at >= timezone.now() - timezone.timedelta(minutes=5)
    
    @property
    def is_paired(self):
        return self.billboard_id is not None

    def save(self, *args, **kwargs):
        # Ensure pairing code is unique
        if not self.pairing_code:
            while True:
                code = self._generate_pairing_code()
                if not PlayerDevice.objects.filter(pairing_code=code).exists():
                    self.pairing_code = code
                    break
        # Ensure auth token is unique
        if not self.auth_token:
            while True:
                token = secrets.token_urlsafe(48)
                if not PlayerDevice.objects.filter(auth_token=token).exists():
                    self.auth_token = token
                    break
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new:
            from scheduling.models import BillboardCapacity
            BillboardCapacity.objects.get_or_create(
                billboard=self,
                defaults={
                    "max_slots_per_day": 10,
                    "slot_duration_seconds": 30,
                }
            )
    @staticmethod
    def _generate_pairing_code():
        clean_letters = "ABCDEFGHJKLMNPQRSTUVWXYZ"
        clean_digits = "23456789"
        letters = "".join(secrets.choice(clean_letters) for _ in range(3))
        digits = "".join(secrets.choice(clean_digits) for _ in range(4))
        
        return f"{letters}-{digits}"

    # Assign this player to a billboard and reset to pending until first heartbeat
    def pair_to_billboard(self, billboard: billboard ): # type: ignore
        self.billboard = billboard
        self.status = self.Status.PENDING
        self.save(update_fields=["billboard", "status", "updated_at"])

    def mark_heartbeat(self, firmware_version="", free_storage_mb=None, current_media_id=None):
        self.last_seen_at = timezone.now()
        self.status = self.Status.ACTIVE
        update_fields = ["last_seen_at", "status", "updated_at"]
        if firmware_version:
            self.firmware_version = firmware_version
            update_fields.append("firmware_version")
        self.save(update_fields=update_fields)
    
    # Called once when the box first fetches its auth_token. Marks it as claimed.
    def claim_token(self):
        if not self.token_claimed_at:
            self.token_claimed_at = timezone.now()
            self.save(update_fields=["token_claimed_at", "updated_at"])

    def rotate_token(self):
        self.auth_token = secrets.token_urlsafe(48)
        self.token_claimed_at = None  
        self.save(update_fields=["auth_token", "token_claimed_at", "updated_at"])

    def disable(self):
        self.status = self.Status.DISABLED
        self.save(update_fields=["status", "updated_at"])

    def unpair(self):
        """
        Detach this device from its billboard, freeing the billboard up
        for a new device to be paired. Does NOT disable the device itself —
        a freshly unpaired device stays in its current status (e.g. still
        ACTIVE) until it's either re-paired or explicitly disabled.
 
        Use this when swapping hardware: unpair the old device, pair a
        new one to the same billboard, then disable() the old device
        separately once you're done with it (keeps audit history intact).
        """
        self.billboard = None
        self.status = self.Status.PENDING
        self.save(update_fields=["billboard", "status", "updated_at"])
    
    def __str__(self):
        paired_to = self.billboard.name if self.billboard_id else "unpaired"
        return f"Player [{self.device_uid}] → {paired_to}"
    
    class Meta:
        indexes = [
            models.Index(fields=["device_uid"]),
            models.Index(fields=["status"]),
            models.Index(fields=["last_seen_at"]),
            models.Index(fields=["pairing_code"]),
        ]

class PlaybackLog(TimeStampedModel):
    # One row per ad play. Drives billing and analytics.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    player = models.ForeignKey(PlayerDevice, on_delete=models.CASCADE, related_name="playback_logs")
    time_slot = models.ForeignKey("scheduling.TimeSlot", on_delete=models.SET_NULL, null=True, blank=True, related_name="playback_logs", help_text="The scheduled slot this play fulfilled, if it matched one.")
    media_id = models.UUIDField(db_index=True)
    started_at = models.DateTimeField()
    duration_seconds = models.PositiveIntegerField()
    completed = models.BooleanField(default=False)

    def __str__(self):
        return f"PlaybackLog [{self.player.device_uid}] media={self.media_id}"
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["player", "media_id", "started_at"],
                name="unique_playback_per_player_media_start",
            )
        ]
        indexes = [
            models.Index(fields=["player", "started_at"]),
            models.Index(fields=["media_id"]),
        ]

class DeviceMetric(TimeStampedModel):
    """Point-in-time hardware health snapshot."""

    id  = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    player = models.ForeignKey(PlayerDevice, on_delete=models.CASCADE, related_name="metrics")
    cpu_usage_pct = models.FloatField(null=True, blank=True)
    ram_usage_mb = models.PositiveIntegerField(null=True, blank=True)
    free_storage_mb  = models.PositiveIntegerField(null=True, blank=True)
    temperature_celsius = models.FloatField(null=True, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Metric [{self.player.device_uid}] @ {self.recorded_at}"

    class Meta:
        indexes = [models.Index(fields=["player", "recorded_at"])]