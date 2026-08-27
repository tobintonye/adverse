from django.db import models, transaction
import uuid
from datetime import date, timedelta, datetime
from django.utils import timezone
from common.models import TimeStampedModel
from advertiser.models import Campaign
"""  
Scheduling engine — decides what plays, when, and where.
 
Scheduling engine for DOOH billboards.
Generates repeating rotation loops based on dayparts rather than fixed clock-time slots.
"""
class ScheduleGenerationError(Exception):
    """Raised when a campaign's date range can't be fully scheduled.
        Carries the list of (billboard, date) conflicts for display to the user."""
    def __init__(self, message, conflicts=None):
        super().__init__(message)
        self.conflicts = conflicts or []
        
class TimeSlot(TimeStampedModel):
  # Represents one rotation loop position for a campaign on a specific billboard and date.
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  billboard = models.ForeignKey("device.Billboard", on_delete=models.CASCADE, related_name="time_slots",) 
  campaign = models.ForeignKey("advertiser.Campaign",on_delete=models.CASCADE, related_name="time_slots",)
  campaign_slot = models.ForeignKey("advertiser.CampaignSlot", on_delete=models.CASCADE, related_name="time_slots",)
  date = models.DateField(db_index=True)
  scheduled_time = models.TimeField(db_index=True, null=True, blank=True) # Deprecated: Retained for historical records; ordering is now driven by play_order.
  play_order = models.PositiveIntegerField() 
  duration_seconds = models.PositiveIntegerField()
  is_active = models.BooleanField(default=True)

  def __str__(self): 
    return (f"{self.billboard.name} | {self.date} | " f"pos #{self.play_order} | {self.campaign.name}")
  
  class Meta: 
    # Exactly one campaign can occupy a given rotation position, on a given
    # billboard, on a given date. This is the real physical double-booking
    # guard now no two advertisers can ever be assigned the same loop slot.
    unique_together = [("billboard", "date", "play_order")]
    indexes = [
            models.Index(fields=["billboard", "date", "is_active"]),
            models.Index(fields=["billboard", "date", "play_order"]),
            models.Index(fields=["campaign", "date"]),
            models.Index(fields=["date"]),
    ] 

class BillboardCapacity(TimeStampedModel):
    """
    Cached daily capacity per billboard.

    max_concurrent_positions = how many DISTINCT advertiser positions can
    share one rotation loop at the same time, on the same daypart, before
    the screen is considered sold out for that window. This is the real
    DOOH inventory constraint — it's a small number (e.g. 6-10), not a
    count of clock-time seats. Fewer concurrent positions = each advertiser
    plays more often = more valuable/expensive inventory; more concurrent
    positions = cheaper but less frequent plays per advertiser. This is a
    pricing lever the ad manager sets per billboard, not something derived
    from operating hours.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    billboard = models.OneToOneField("device.Billboard", on_delete=models.CASCADE, related_name="capacity",)
    max_concurrent_positions = models.PositiveIntegerField(default=8, help_text="How many advertiser positions can share the rotation loop at once, for any given daypart, before this billboard is sold out.")
    # Deprecated: Retained for backward compatibility.
    max_slots_per_day = models.PositiveIntegerField(default=0)
    slot_duration_seconds = models.PositiveBigIntegerField(default=30)
    last_calculated_at   = models.DateTimeField(auto_now=True)

    def recalculate(self, max_concurrent_positions=None):
        """Set how many concurrent rotation positions this
        billboard sells. Unlike the old grid-based version, this isn't derived
        from operating hours math — it's a direct inventory decision."""
        if max_concurrent_positions is not None:
            self.max_concurrent_positions = max_concurrent_positions
        self.save(update_fields=["max_concurrent_positions", "last_calculated_at"])
        return self.max_concurrent_positions

    def positions_used_on(self, target_date, daily_start_time=None, daily_end_time=None):
        """
        How many rotation positions are already claimed on this billboard for
        the given date, restricted to campaigns whose OWN daypart overlaps the
        given window (or all active positions that day if no window given).
        Two campaigns only compete for the same positions if their dayparts
        actually overlap — a 6-9am campaign and a 9pm-midnight campaign never
        share a rotation, so they never compete for the same capacity.
        """
        qs = TimeSlot.objects.filter(
            billboard=self.billboard, date=target_date, is_active=True,
        )
        if daily_start_time is not None and daily_end_time is not None:
            qs = qs.filter(
                campaign__daily_start_time__lt=daily_end_time,
                campaign__daily_end_time__gt=daily_start_time,
            )
        return qs.count()
    
    def available_positions_on(self, target_date, daily_start_time=None, daily_end_time=None):
        used = self.positions_used_on(target_date, daily_start_time, daily_end_time)
        return max(0, self.max_concurrent_positions - used)

    def __str__(self):
        return f"{self.billboard.name} — {self.max_concurrent_positions} concurrent positions"

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

def _weighted_round_robin_order(weights):
    """
    Given {key: weight}, returns a list of keys where each key appears
    `weight` times, interleaved as evenly as possible across the whole
    sequence. This is the rotation-loop analog of the old clock-time
    _pick_evenly_spaced() — instead of spreading N bookings across a time
    grid, it spreads N repeats of each campaign_slot evenly across the
    day's loop, so a campaign that bought 3 positions doesn't play three
    times in a row back-to-back, and a campaign that bought 1 position
    isn't always shoved to the very end.

    e.g. {"A": 3, "B": 1} -> roughly ["A", "A", "B", "A"]
    """
    items = []
    for key, weight in weights.items():
        if weight <= 0:
            continue
        for i in range(weight):
            # fractional position within [0, 1) — evenly spaced occurrences
            # of this key, same technique as the old _pick_evenly_spaced.
            items.append(((i + 0.5) / weight, key))
    items.sort(key=lambda pair: pair[0])
    return [key for _, key in items]

def check_capacity(billboard, start_date, end_date, slots_per_day, daily_start_time, daily_end_time):
    """
    Returns (ok, conflicts). Checks whether enough rotation positions are
    still open, for every day in the range, among campaigns whose daypart
    actually overlaps this request's daypart.
    """
    try:
       capacity = billboard.capacity
    except BillboardCapacity.DoesNotExist:
       return False, [start_date]

    conflicts = []
    current = start_date
    while current <= end_date:
        available = capacity.available_positions_on(current, daily_start_time, daily_end_time)
        if available < slots_per_day:
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
    
    # All clear actually create every TimeSlot row, rebalancing each
    # affected day's rotation order.
    slots_created = 0
    current_date = campaign.start_date
    while current_date <= campaign.end_date:
        for cs in campaign_slots:
            billboard = cs.billboard
            _rebalance_day(billboard, current_date, new_campaign_slot=cs, new_weight=cs.slots_per_day)
            slots_created += cs.slots_per_day
        current_date += timedelta(days=1)

    ScheduleGenerationLog.objects.create(
        campaign=campaign,
        result=ScheduleGenerationLog.Result.SUCCESS,
        slots_created=slots_created,
        slots_skipped=0,
    )
    return slots_created

def _rebalance_day(billboard, target_date, new_campaign_slot=None, new_weight=0):
    # Recomputes and recreates TimeSlot play orders for a billboard on a specific date.
   
    existing = (
        TimeSlot.objects
        .filter(billboard=billboard, date=target_date, is_active=True)
        .select_related("campaign", "campaign_slot")
    )

    # weight per campaign_slot = how many positions it should hold that day
    weights = {}
    slot_lookup = {}
    duration_lookup = {}
    for ts in existing:
        cs = ts.campaign_slot
        weights[cs.id] = weights.get(cs.id, 0) + 1
        slot_lookup[cs.id] = cs
        duration_lookup[cs.id] = ts.duration_seconds

    if new_campaign_slot is not None and new_weight > 0:
        weights[new_campaign_slot.id] = weights.get(new_campaign_slot.id, 0) + new_weight
        slot_lookup[new_campaign_slot.id] = new_campaign_slot
        duration_lookup[new_campaign_slot.id] = (
            new_campaign_slot.campaign.media.duration_seconds or 10
        )

    if not weights:
        return

    order = _weighted_round_robin_order(weights)

    # Rebuild: delete existing rows for this billboard/date, recreate fresh
    # with the new fairly-interleaved play_order.
    existing.delete()
    new_rows = [
        TimeSlot(
            billboard=billboard,
            campaign=slot_lookup[cs_id].campaign,
            campaign_slot=slot_lookup[cs_id],
            date=target_date,
            play_order=i,
            duration_seconds=duration_lookup[cs_id],
        )
        for i, cs_id in enumerate(order)
    ]
    TimeSlot.objects.bulk_create(new_rows)


def get_playlist_for_billboard(billboard, target_date=None):
    """
    Returns active, transcoded TimeSlots ordered by play_order for playback.
    Includes all dayparts to support offline device playback.
    """
    
    if target_date is None:
        target_date = timezone.now().date()
    
    return (
        TimeSlot.objects
        .filter(
            billboard=billboard,
            date=target_date,
            is_active=True,
            campaign__status="active",
            campaign__media__transcode_status="done",
        )
        .select_related("campaign", "campaign__media", "campaign_slot")
        .order_by("play_order")
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
 
