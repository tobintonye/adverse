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
class ScheduleGenerationError(Exception):
    """Raised when a campaign's date range can't be fully scheduled.
    Carries the list of (billboard, date) conflicts for display to the user."""
    def __init__(self, message, conflicts=None):
        super().__init__(message)
        self.conflicts = conflicts or []
        
class TimeSlot(TimeStampedModel):
  # one allocated play of one campaign's ad on one billboard on one date(stores every scheduled advertisement play.)
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  billboard = models.ForeignKey("device.Billboard", on_delete=models.CASCADE, related_name="time_slots",) 
  campaign = models.ForeignKey("advertiser.Campaign",on_delete=models.CASCADE, related_name="time_slots",)
  campaign_slot = models.ForeignKey("advertiser.CampaignSlot", on_delete=models.CASCADE, related_name="time_slots",)
  date = models.DateField(db_index=True)
  scheduled_time = models.TimeField(db_index=True, help_text=" The real clock time this exact play is scheduled for what the device actually checks against, not jst an " \
  "ordering position. An advertiser's 7am - 9am window only ever gets seats whose scheduled_time actually falls in 7am-9am", null=True, blank=True)
  play_order = models.PositiveIntegerField()   # position in the day's rotation
  duration_seconds = models.PositiveIntegerField()
  is_active = models.BooleanField(default=True)

  def __str__(self): 
    return (f"{self.billboard.name} | {self.date} | " f"#{self.scheduled_time} | {self.campaign.name}")
  
  class Meta: 
   # one scheduled_time per billboard per day this is the real physical
   # double-booking guard now. prevents campains windows from landing on the same clock second.
    unique_together = [("billboard", "date", "scheduled_time")]
    indexes = [
            models.Index(fields=["billboard", "date", "is_active"]),
            models.Index(fields=["campaign", "date", "scheduled_time"]),
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
    self.slot_duration_seconds = slot_duration_seconds  
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
  campaign = models.ForeignKey("advertiser.Campaign", on_delete=models.CASCADE, related_name="schedule_logs",)
  result = models.CharField(max_length=20, choices=Result.choices)
  slots_created = models.PositiveIntegerField(default=0)
  slots_skipped = models.PositiveIntegerField(default=0) 
  error_message = models.TextField(blank=True)
  generated_at = models.DateTimeField(auto_now_add=True)

  def __str__(self):
        return f"ScheduleLog [{self.campaign.name}] {self.result} — {self.slots_created} slots"

def _window_seat_times(window_start, window_end, slot_duration_seconds):
    """
    Every fixed clock-time 'seat' in a window, quantized to slot_duration_seconds
    e.g 7:00-9:00 at 30s => [7:00:00, 7:00:30, 7:01:00, ... 8:59:30]
    This is the shared grid every campaign wanting that window draws from the mechanism that make two advertisers
    7-9am booking never collide.
    """
    start_dt = datetime.combine(date.today(), window_start)
    end_dt = datetime.combine(date.today(), window_end)
    total_seconds = int((end_dt - start_dt).total_seconds())
    seat_count = total_seconds // slot_duration_seconds
    return [
       (start_dt + timedelta(seconds=i * slot_duration_seconds)).time() 
       for i in range(seat_count)
    ]

def _available_seats_in_window(billboard, target_date, window_start, window_end, slot_duration_seconds):
    """Seats in this window not already claimed by ANY campaign that day."""
    all_seats = _window_seat_times(window_start, window_end, slot_duration_seconds)
    taken = set(
        TimeSlot.objects.filter(
            billboard=billboard, date=target_date, is_active=True,
            scheduled_time__gte=window_start, scheduled_time__lt=window_end,
        ).values_list("scheduled_time", flat=True)
    )
    return [t for t in all_seats if t not in taken]

def _pick_evenly_spaced(available_seats, count):
    """
    Picks 'count' seats spreads as evenly as possible across whatever seats are still open not across the whole window. This is what lets a second advertiser in the same window
    get a fail, non-colliding spread of whatever's left, rather than just grabbing the first N free seats  
    """
    if count <= 0:
       return []
    if count >= len(available_seats):
       return list(available_seats)
    step = len(available_seats) / count
    return [available_seats[int(i * step)] for i in range(count)]

def check_capacity(billboard, start_date, end_date, slots_per_day, daily_start_time, daily_end_time):
    """
    Returns (ok, conflicts). Checks if enough open slots exist per day within
    the target daypart window between start_date and end_date.
    """
    try:
       capacity = billboard.capacity
    except BillboardCapacity.DoesNotExist:
       return False, [start_date]

    conflicts = []
    current = start_date
    while current <= end_date:
        available = _available_seats_in_window(billboard, current, daily_start_time, daily_end_time, capacity.slot_duration_seconds)
        if len(available) < slots_per_day:
           conflicts.append(current)
        current += timedelta(days=1)
    return len(conflicts) == 0, conflicts

@transaction.atomic
def generate_schedule(campaign):
    """
    Called after the advertiser confirms real calendar dates (post-approval).
    All-or-nothing: pre-checks capacity for every day across every billboard
    slot BEFORE creating any TimeSlot rows. If any day anywhere is short on
    capacity, nothing is created and ScheduleGenerationError is raised
    the caller (confirm_campaign_dates) rolls back the date assignment too.
    """
 
    campaign_slots = campaign.campaign_slots.select_related(
        "billboard", "billboard__capacity"
    ).all()
    
    if not campaign_slots:
        raise ScheduleGenerationError("Campaign has no billboard slots assigned.")
    
     # Pre-flight: check every slot's full date range before touching the DB
    all_conflicts = []  # list of (billboard, date) tuples
    for cs in campaign_slots:
       ok, conflicts = check_capacity(
          cs.billboard, campaign.start_date, campaign.end_date, cs.slots_per_day, campaign.daily_start_time, campaign.daily_end_time
       )
       if not ok:
            all_conflicts.extend((cs.billboard, d) for d in conflicts)

    if all_conflicts:
        ScheduleGenerationLog.objects.create(
            campaign=campaign,
            result=ScheduleGenerationLog.Result.FAILED,
            slots_created=0,
            slots_skipped=len(all_conflicts),
            error_message=(
                f"{len(all_conflicts)} date(s) had insufficient capacity: "
                + ", ".join(f"{b.name} on {d}" for b, d in all_conflicts[:10])
                + ("..." if len(all_conflicts) > 10 else "")
            ),
        )
        raise ScheduleGenerationError(
            f"{len(all_conflicts)} date(s) in your chosen range are unavailable "
            f"on one or more billboards. Please pick a different date range.",
            conflicts=all_conflicts,
        )
    
    # All clear now actually create every TimeSlot row 
    slots_created = 0
    current_date = campaign.start_date
    while current_date <= campaign.end_date:
        for cs in campaign_slots:
            billboard = cs.billboard
            capacity = billboard.capacity
            last_order = TimeSlot.objects.filter(
                billboard=billboard, date=current_date, is_active=True,
            ).aggregate(models.Max("play_order"))["play_order__max"] or 0

            available = _available_seats_in_window(
               billboard, current_date, campaign.daily_start_time, campaign.daily_end_time, capacity.slot_duration_seconds,
            )
            chosen_times = _pick_evenly_spaced(available, cs.slots_per_day)
            for i, scheduled_time in enumerate(chosen_times):
                TimeSlot.objects.create(
                    billboard=billboard,
                    campaign=campaign,
                    campaign_slot=cs,
                    date=current_date,
                    scheduled_time=scheduled_time,
                    play_order = last_order + i + 1, # legacy display ordering only
                    duration_seconds=campaign.media.duration_seconds or 30,
                )
                slots_created += 1
        current_date += timedelta(days=1)
    ScheduleGenerationLog.objects.create(
        campaign=campaign,
        result=ScheduleGenerationLog.Result.SUCCESS,
        slots_created=slots_created,
        slots_skipped=0,
    )
    return slots_created
def get_playlist_for_billboard(billboard, target_date=None):
    """Returns the ordered list of active TimeSlots for a billboard on a given date."""
    
    if target_date is None:
        target_date = timezone.now().date()
 
    return (
        TimeSlot.objects
        .filter(
            billboard=billboard,
            date=target_date,
            is_active=True,
            #campaign__status__in=["approved", "active"],
            campaign__status="active", 
            campaign__media__transcode_status="done",
        )
        .select_related("campaign", "campaign__media", "campaign_slot")
        .order_by("scheduled_time")
    )
 

def expire_campaigns():
    """
    Mark campaigns as completed when end_date has passed.
    Called by a scheduled task (e.g. Celery beat, cron) run daily.
    """

    today = timezone.now().date()
    expired = Campaign.objects.filter(
        status=Campaign.Status.ACTIVE,
        end_date__lt=today,
    )
    count = expired.update(status=Campaign.Status.COMPLETED)
    return count
 
