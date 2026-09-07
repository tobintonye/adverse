from django.db import models, transaction
import uuid
from datetime import date, timedelta, datetime
from django.utils import timezone
from common.models import TimeStampedModel
from advertiser.models import Campaign
from django.db.models import Q, F

"""
Scheduling engine — decides what plays, when, and where.

REDESIGNED to match how real DOOH (digital out-of-home) billboards actually
work: a continuously repeating ROTATION, not a set of exact clock-time
bookings. Every campaign active *right now* (correct date range AND within
its own daily daypart window) gets one or more POSITIONS in a repeating
loop. The screen plays through the loop continuously and never goes idle
during operating hours as long as at least one campaign is active.

A TimeSlot row no longer means "play at exactly this clock time" — it means
"this campaign occupies position N in today's rotation for this billboard."
play_order is the real, used ordering field now (previously described as
"legacy display ordering only" — that's no longer true, it drives playback).

Flow triggered by campaign approval:
  manager_approve(campaign) → generate_schedule(campaign) → TimeSlot rows created
"""


def _daypart_overlap_q(window_start, window_end, field_prefix="campaign__"):
    """
    Returns a Q object to check if a row's daypart overlaps a given [window_start, window_end).

    Handles overnight/past-midnight intervals for both the row's daypart and the target window:
    - Neither wraps: standard range overlap (start_a < end_b AND end_a > start_b)
    - Exactly one wraps: split range overlap (start_a < end_b OR end_a > start_b)
    - Both wrap: guaranteed overlap (both active at midnight)
    """
    start_f, end_f = f"{field_prefix}daily_start_time", f"{field_prefix}daily_end_time"
    row_no_wrap = Q(**{f"{start_f}__lt": F(end_f)})
    row_wraps = Q(**{f"{start_f}__gte": F(end_f)})

    start_lt_window_end = Q(**{f"{start_f}__lt": window_end})
    end_gt_window_start = Q(**{f"{end_f}__gt": window_start})

    window_wraps = window_start > window_end    

    if window_wraps:
        return row_wraps | (row_no_wrap & (start_lt_window_end | end_gt_window_start))
    else:
        return (row_no_wrap & start_lt_window_end & end_gt_window_start) | (
            row_wraps & (start_lt_window_end | end_gt_window_start)
        )

class ScheduleGenerationError(Exception):
    """Raised when a campaign's date range can't be fully scheduled.
    Carries the list of (billboard, date) conflicts for display to the user."""
    def __init__(self, message, conflicts=None):
        super().__init__(message)
        self.conflicts = conflicts or []

class TimeSlot(TimeStampedModel):
  # One rotation position: this campaign gets one play, once per loop cycle,
  # on this billboard, on this date, for as long as "now" falls within the
  # campaign's own daily_start_time/daily_end_time daypart (read off the
  # related Campaign — not stored per-row, since it's the same for every
  # row a given campaign owns).
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  billboard = models.ForeignKey("device.Billboard", on_delete=models.CASCADE, related_name="time_slots",)
  campaign = models.ForeignKey("advertiser.Campaign",on_delete=models.CASCADE, related_name="time_slots",)
  campaign_slot = models.ForeignKey("advertiser.CampaignSlot", on_delete=models.CASCADE, related_name="time_slots",)
  date = models.DateField(db_index=True)
  # DEPRECATED — no longer set by generate_schedule(), kept only so historical
  # rows created before this redesign remain readable. Rotation position is
  # now driven entirely by play_order. Do not write to this field.
  scheduled_time = models.TimeField(db_index=True, null=True, blank=True)
  # The real field that matters now: this campaign's position in today's
  # rotation for this billboard. unique_together below is the double-booking
  # guard — exactly one campaign can hold position N on a given billboard/date.
  play_order = models.PositiveIntegerField()
  duration_seconds = models.PositiveIntegerField()
  is_active = models.BooleanField(default=True)

  def __str__(self):
    return (f"{self.billboard.name} | {self.date} | " f"pos #{self.play_order} | {self.campaign.name}")

  class Meta:
    # Exactly one campaign can occupy a given rotation position, on a given
    # billboard, on a given date. This is the real physical double-booking
    # guard now — no two advertisers can ever be assigned the same loop slot.
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

    Think of a billboard's rotation as a loop with a fixed number of
    "seats" — max_concurrent_positions is how many seats exist. Every
    seat repeats once per loop cycle, so fewer seats means each one
    comes around more often (more valuable), and more seats means
    cheaper but less frequent plays.

    Example: a billboard has 8 seats.
        - Advertiser A buys 1 seat  -> 7 remain for everyone else.
        - Advertiser B buys 3 seats -> 4 remain.
        - Advertiser C could buy all remaining 4, or even all 8 up front
        (a full buyout, 100% share of voice) — nothing stops one
        advertiser from taking the whole loop.

    So this is a SHARED POOL of seats, not "one seat per advertiser."
    An advertiser's own Ad Slots Per Day (slots_per_day) is simply how
    many seats from this pool they're claiming.

    This number is a pricing lever the ad manager sets directly per
    billboard (e.g. 6-10) — it has nothing to do with operating hours
    or how long the screen runs each day.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    billboard = models.OneToOneField("device.Billboard", on_delete=models.CASCADE, related_name="capacity",)
    max_concurrent_positions = models.PositiveIntegerField(
        default=8,
        help_text="Total number of rotation-loop positions this billboard sells for any "
                "given daypart, before it's sold out. This is a shared pool, not a "
                "per-advertiser count — one advertiser's Ad Slots Per Day claims that "
                "many positions from this same total, so a single advertiser CAN buy "
                "the entire capacity (a full buyout), leaving none for anyone else."
    )
    # Kept for backward compatibility / historical reporting only
    max_slots_per_day = models.PositiveIntegerField(default=0)
    slot_duration_seconds = models.PositiveBigIntegerField(default=30)
    last_calculated_at   = models.DateTimeField(auto_now=True)

    def recalculate(self, max_concurrent_positions=None):
        """Set (or re-affirm) how many concurrent rotation positions this
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
            qs = qs.filter(_daypart_overlap_q(daily_start_time, daily_end_time))
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
    capacity, nothing is created and ScheduleGenerationError is raised —
    the caller (confirm_campaign_dates) rolls back the date assignment too.

    Unlike the old exact-time version, adding a new campaign to a day that
    already has other active campaigns REBALANCES the whole day's rotation
    order for that billboard — every campaign sharing that day's loop gets
    its play_order recomputed so the new campaign is fairly interleaved in,
    not just appended at the end. This matches how real rotation loops work:
    the loop composition (and therefore each advertiser's play frequency)
    changes whenever the set of active advertisers changes.
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

    # All clear — actually create every TimeSlot row, rebalancing each
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
    """
    Recomputes the full rotation order for one billboard/date, given every
    campaign_slot that should have a position that day (existing active ones
    on that billboard/date, plus optionally one new one being added).

    Deletes and recreates every TimeSlot row for that billboard/date — rows
    are interchangeable position-holders, not identity-bearing records, so
    this is safe. (PlaybackLog.time_slot is on_delete=SET_NULL, so historical
    playback logs are preserved even though their TimeSlot FK goes null.)
    """
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
            new_campaign_slot.campaign.media.duration_seconds or 30
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
    Returns every active rotation position for a billboard on a given date,
    ordered for rotation playback. Includes campaigns across ALL dayparts —
    the device is responsible for filtering to "eligible right now" based on
    each campaign's daily_start_time/daily_end_time and its own clock, same
    "clock-driven, not self-timed" principle the player already uses. This
    keeps the device fully offline-resilient: it caches the whole day's
    rotation membership up front and doesn't need to re-poll every time a
    daypart boundary crosses.
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