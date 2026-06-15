from django.db import models, transaction
import uuid
from datetime import date, timedelta, datetime
from django.utils import timezone
from common.models import TimeStampedModel
from advertiser.models import Campaign
"""  
Scheduling engine — decides what plays, when, and where.
 
Flow triggered by campaign approval:
  manager_approve(campaign) → generate_schedule(campaign) → TimeSlot rows created
"""

class TimeSlot(TimeStampedModel):
  # one allocated play of one campaign's ad on one billboard on one date(stores every scheduled advertisement play.)
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  billboard = models.ForeignKey("device.Billboard", on_delete=models.CASCADE, related_name="time_slots",) 
  campaign = models.ForeignKey("advertiser.Campaign",on_delete=models.CASCADE, related_name="time_slots",)
  campaign_slot = models.ForeignKey("advertiser.CampaignSlot", on_delete=models.CASCADE, related_name="time_slots",)
  date = models.DateField(db_index=True)
  play_order = models.PositiveIntegerField()   # position in the day's rotation
  duration_seconds = models.PositiveIntegerField()
  is_active = models.BooleanField(default=True)

  def __str__(self): 
    return (f"{self.billboard.name} | {self.date} | " f"#{self.play_order} | {self.campaign.name}")
  
  class Meta: 
    # One play_order position per billboard per day — prevents double-booking
    unique_together = [("billboard", "date", "play_order")]
    indexes = [
            models.Index(fields=["billboard", "date", "is_active"]),
            models.Index(fields=["campaign", "date"]),
            models.Index(fields=["date"]),
    ] 

class BillboardCapacity(TimeStampedModel):
  """
    Cached daily capacity per billboard -> total number of ad slots a billboard can play in a day
    Recalculated when operating hours or slot duration changes.
 
    max_slots_per_day = floor(operating_seconds / slot_duration_seconds)
  """
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  billboard = models.OneToOneField("device.Billboard", on_delete=models.CASCADE, related_name="capacity",)
  max_slots_per_day = models.PositiveIntegerField(default=0)
  slot_duration_seconds = models.PositiveBigIntegerField(default=30)
  last_calculated_at   = models.DateTimeField(auto_now=True)

  def recalculate(self, slot_duration_seconds=30): 
    # Recalculate based on billboard operating hours.
    b = self.billboard
    start = datetime.combine(date.today(), b.operating_hours_start)
    end = datetime.combine(date.today(), b.operating_hours_end)
    operating_seconds = (end - start).seconds
    self.slot_durations_seconds = slot_duration_seconds
    self.max_slots_per_day = operating_seconds // slot_duration_seconds
    self.save(update_fields=["max_slots_per_day", "slot_duration_seconds", "last_calculated_at"])
    return self.max_slots_per_day
  
  def available_slots_on(self, target_date):
    # How many free slots are left on a given day
    booked = TimeSlot.objects.filter(billboard=self.billboard, date=target_date, is_active=True).count()
    return max(0, self.max_slots_per_day - booked)
    
  def __str__(self):
    return f"{self.billboard.name} — {self.max_slots_per_day} slots/day"

class ScheduleGenerationLog(TimeStampedModel):
  """
    Audit trail for every schedule generation run.
    Helps debug why a campaign has missing slots.
  """
  class Result(models.TextChoices):
      SUCCESS = "success", "Success"
      PARTIAL = "partial", "Partial (some dates had no capacity)"
      FAILED  = "failed",  "Failed"
 
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  campaign = models.ForeignKey("advertiser.CampaignSlot", on_delete=models.CASCADE, related_name="schedule_logs",)
  result = models.CharField(max_length=20, choices=Result.choices)
  slots_created = models.PositiveIntegerField(default=0)
  slots_skipped = models.PositiveIntegerField(default=0) 
  error_message = models.TextField(blank=True)
  generated_at = models.DateTimeField(auto_now_add=True)

  def __str__(self):
        return f"ScheduleLog [{self.campaign.name}] {self.result} — {self.slots_created} slots"
  

def check_capacity(billboard, start_date, end_date, slots_per_day): 
  """
    Returns (ok: bool, conflicts: list[date] that are over booked)
    Checks every date in the range has enough free capacity.
  """

  try: 
     capacity = billboard.capacity
  except BillboardCapacity.DoesNotExist:
     return False, [start_date]
  
  conflicts = [] 
  current = start_date
  while current <= end_date: 
    available = capacity.available_slots_on(current)
    if available < slots_per_day: 
       conflicts.append(current)
    current += timedelta(days=1)
  return len(conflicts) == 0, conflicts

@transaction.atomic
def generate_schedule(campaign):
    """
    Called when a campaign is approved by the ad manager.
    Creates TimeSlot rows for every day in the campaign date range.
 
    Strategy:
      - For each day, find the next available play_order positions on each billboard.
      - If a billboard is full on a given day, skip that day and log it.
    """
    slots_created = 0
    slots_skipped = 0
 
    campaign_slots = campaign.campaign_slots.select_related(
        "billboard", "billboard__capacity"
    ).all()
 
    current_date = campaign.start_date
    while current_date <= campaign.end_date:
        for cs in campaign_slots:
            billboard = cs.billboard
 
            # Find highest play_order already allocated on this date
            last_order = TimeSlot.objects.filter(
                billboard=billboard,
                date=current_date,
                is_active=True,
            ).aggregate(models.Max("play_order"))["play_order__max"] or 0
 
            # Check capacity
            try:
                max_slots = billboard.capacity.max_slots_per_day
            except BillboardCapacity.DoesNotExist:
                slots_skipped += cs.slots_per_day
                continue
 
            already_booked = TimeSlot.objects.filter(
                billboard=billboard,
                date=current_date,
                is_active=True,
            ).count()
 
            free_slots = max_slots - already_booked
            to_allocate = min(cs.slots_per_day, free_slots)
            skipped     = cs.slots_per_day - to_allocate
 
            for i in range(to_allocate):
                TimeSlot.objects.create(
                    billboard=billboard,
                    campaign=campaign,
                    campaign_slot=cs,
                    date=current_date,
                    play_order=last_order + i + 1,
                    duration_seconds=campaign.media.duration_seconds or 30,
                )
                slots_created += 1
 
            slots_skipped += skipped
 
        current_date += timedelta(days=1)
 
    result = (
        ScheduleGenerationLog.Result.SUCCESS if slots_skipped == 0
        else ScheduleGenerationLog.Result.PARTIAL
    )
 
    ScheduleGenerationLog.objects.create(
        campaign=campaign,
        result=result,
        slots_created=slots_created,
        slots_skipped=slots_skipped,
    )
 
    return slots_created, slots_skipped

def get_playlist_for_billboard(billboard, target_date=None):
    """
    Returns the ordered list of active TimeSlots for a billboard on a given date.
    Called by the device schedule endpoint.
    """
    if target_date is None:
        target_date = timezone.now().date()
 
    return (
        TimeSlot.objects
        .filter(
            billboard=billboard,
            date=target_date,
            is_active=True,
            campaign__status__in=["approved", "active"],
        )
        .select_related("campaign", "campaign__media", "campaign_slot")
        .order_by("play_order")
    )
 

def expire_campaigns():
    """
    Mark campaigns as completed when end_date has passed.
    Called by a scheduled task (e.g. Celery beat, cron) — run daily.
    """

    today = timezone.now().date()
    expired = Campaign.objects.filter(
        status=Campaign.Status.ACTIVE,
        end_date__lt=today,
    )
    count = expired.update(status=Campaign.Status.COMPLETED)
    return count
 
 
def activate_campaigns():
    """
    Mark approved campaigns as active when start_date arrives.
    Called by the same daily task.
    """
    today = timezone.now().date()
    activated = Campaign.objects.filter(
        status=Campaign.Status.APPROVED,
        start_date__lte=today,
        end_date__gte=today,
    )
    count = activated.update(status=Campaign.Status.ACTIVE)
    return count
