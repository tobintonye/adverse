from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView 
from device.models import Billboard
from advertiser.models import Campaign
from ..models import ( BillboardCapacity, ScheduleGenerationLog, TimeSlot, check_capacity, 
                    generate_schedule, get_playlist_for_billboard,
)
from .serializers import ( BillboardCapacitySerializer, CapacityCheckSerializer, ScheduleGenerationLogSerializer,
                           TimeSlotSerializer,
                        )
from datetime import date as date_type, time, timedelta
from django.db.models import Count

class BillboardScheduleView(APIView):
    """
    GET /scheduling/billboards/<uuid:pk>/schedule/?date=2026-06-01
 
    Preview the full playlist for a billboard on a given date.
    Used by the dashboard — ad managers see what's playing on their screens.
    Also used by the Android box (device schedule endpoint delegates here).
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk): 
        try: 
            billboard = Billboard.objects.get(pk=pk)
        except Billboard.DoesNotExist: 
            raise NotFound("Billboard not found.")
        
        date_param = request.query_params.get("date")
        try:
            target_date = (
                date_type.fromisoformat(date_param)
                if date_param
                else timezone.now().date()
            )
        except ValueError:
            return Response({"detail": "Invalid date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
        slots = get_playlist_for_billboard(billboard, target_date)

        return Response({
            "billboard": billboard.name,
            "date":target_date,
            "total_slots": slots.count(),
            "playlist":TimeSlotSerializer(slots, many=True, context={"request": request}).data
        })
    
class BillboardCapacityView(APIView):
    """
    GET  /scheduling/billboards/<uuid:pk>/capacity/
    POST /scheduling/billboards/<uuid:pk>/capacity/recalculate/
 
    Shows max slots/day and recalculates when operating hours change.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk): 
        try:
            billboard = Billboard.objects.get(pk=pk)
        except Billboard.DoesNotExist:
            raise NotFound("Billboard not found.")
        
        capacity, _ = BillboardCapacity.objects.get_or_create(billboard=billboard)

        available_today = capacity.available_positions_on(timezone.now().date())

        return Response({
            **BillboardCapacitySerializer(capacity).data,
            "available_today": available_today,
        })
  
class BillboardCapacityRecalculateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        if not (request.user.is_staff or request.user.ad_manager):
            raise PermissionDenied("Only admins or ad managers can recalculate capacity.")
        try: 
            billboard = Billboard.objects.get(pk=pk)
        except Billboard.DoesNotExist:
            raise NotFound("Billboard not found.")
        
        max_concurrent_positions = int(request.data.get("max_concurrent_positions", 8))
        capacity, _ = BillboardCapacity.objects.get_or_create(billboard=billboard)
        new_max = capacity.recalculate(max_concurrent_positions=max_concurrent_positions)

        return Response({
            "detail": "Capacity updated.",
            "max_concurrent_positions": new_max,
        })

class BillboardHourlyLoadView(APIView):
    """
    GET /scheduling/billboards/<uuid:pk>/hourly-load/?days_ahead=14

    Returns hourly rotation loop availability across operating hours to help 
    advertisers choose an available daypart during campaign creation (since 
    dayparts cannot be edited after approval).

    Reports the worst-case (busiest single day) load for each hour over the next 
    `days_ahead` days. 

    Limitation: Does not support overnight operating hours or dayparts (e.g. 22:00-06:00).
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk): 
        try:
            billboard = Billboard.objects.get(pk=pk)
        except Billboard.DoesNotExist:
            raise NotFound("Billboard not found")
        try:
            capacity = billboard.capacity
        except BillboardCapacity.DoesNotExist:
            return Response({ "detail": "Capacity not configured for this billboard yet."}, status=status.HTTP_400_BAD_REQUEST,)

        try:
            days_ahead = int(request.query_params.get('days_ahead', 14))
        except ValueError:
            days_ahead = 14
        days_ahead = max(1, min(days_ahead, 60)) # sane bounds not 0, not unbounded

        today = timezone.now().date()
        dates = [today + timedelta(days=i) for i in range(days_ahead)]

        start_hour = billboard.operating_hours_start.hour
        end_hour = billboard.operating_hours_end.hour

        hours = []
        h = start_hour
        while True:
            hours.append(h)
            if h == end_hour:
                break
            h = (h + 1) % 24
            if len(hours) > 24:
                break # safety net against a malformed/overnight-wrapping window

        blocks = []
        for h in hours:
            block_start = time(h, 0)
            max_load = 0
            for d in dates:
                used = TimeSlot.objects.filter(billboard=billboard, date=d, is_active=True, campaign__daily_start_time__lte=block_start, campaign__daily_end_time__gt=block_start).count()
                max_load = max(max_load, used)
            blocks.append({
                "hour": h,
                "label": block_start.strftime("%I:%M %p").lstrip("0"),
                "used": max_load,
                "capacity": capacity.max_concurrent_positions,
                "available": max(0, capacity.max_concurrent_positions - max_load),
                "is_full": max_load >= capacity.max_concurrent_positions,
            })

        return Response({
            "billboard": billboard.name,
            "max_concurrent_positions": capacity.max_concurrent_positions,
            "days_ahead": days_ahead,
            "hours": blocks,
        })

class CapacityCheckView(APIView):
    """
        Check whether a billboard has enough free capacity before booking.
        Called by the frontend during campaign creation — shows availability
        before the advertiser submits.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request): 
        serializer = CapacityCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            billboard  = Billboard.objects.get(pk=serializer.validated_data["billboard_id"])
        except Billboard.DoesNotExist:
            raise NotFound("Billboard not found.")
        
        ok, conflicts = check_capacity(
            billboard,
            serializer.validated_data["start_date"],
            serializer.validated_data["end_date"],
            serializer.validated_data["slots_per_day"],
            serializer.validated_data["daily_start_time"],
            serializer.validated_data["daily_end_time"],
        )

        return Response({
            "billboard": billboard.name, 
            "available": ok, 
            "conflicts": [str(d) for d in conflicts],
             "message": (
                "Billboard has capacity for your entire campaign." if ok
                else f"Billboard is fully booked on {len(conflicts)} day(s)."
            ),
        })


class CampaignScheduleGenerateView(APIView):
    """
        Manually trigger schedule generation for an approved campaign.
        Normally this is called automatically via signal on approval,
        but admins can re-trigger if something went wrong.`
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk): 
        if not request.user.is_staff or request.user.ad_manager: 
            raise PermissionDenied("Only admins and ad managers can trigger schedule generation.")
        
        try:
            campaign = Campaign.objects.get(pk=pk)
        except Campaign.DoesNotExist: 
            raise NotFound("Campaign not found.")
        
        if campaign.status not in [Campaign.Status.APPROVED, Campaign.Status.ACTIVE]:
            return Response({
                "detail": "Campaign must be approved or active to generate a schedule."
            }, status=status.HTTP_400_BAD_REQUEST,)
        
        # Clear existing slots before regenerating
        TimeSlot.objects.filter(campaign=campaign).delete()
        created, skipped = generate_schedule(campaign)

        return Response({
            "detail": "Schedule generated.",
            "slots_created": created,
            "slots_skipped": skipped,
            "warning": (
                f"{skipped} slots were skipped due to insufficient billboard capacity."
                if skipped else None
            ),
        })

class CampaignSchedulePreviewView(APIView): 
    """
        Advertiser previews their schedule before it goes live.
        Shows how many slots are allocated per billboard per day.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        try: 
            campaign = Campaign.objects.prefetch_related("campaign_slots__billboard").get(pk=pk)
        except Campaign.DoesNotExist:
            raise NotFound("Campaign not found.")
        
        # Ownership — advertiser sees their own, staff sees all
        if not request.user.is_staff:
            try: 
                if campaign.advertiser.user != request.user:
                    raise PermissionDenied("You do not own this campaign.")
            except Exception:
                raise PermissionDenied("You do not own this campaign.")
        
        slots = TimeSlot.objects.filter(
            campaign=campaign,
            is_active=True,
        ).values("billboard__name", "date").annotate(slot_count=Count("id")).order_by("date", "billboard__name")

        log = ScheduleGenerationLog.objects.filter(
            campaign=campaign
        ).order_by("-generated_at").first()

        return Response({
            "campaign": campaign.name,
            "status": campaign.status,
            "start_date": campaign.start_date,
            "end_date": campaign.end_date,
            "total_slots": TimeSlot.objects.filter(campaign=campaign, is_active=True).count(),
            "daily_summary":  list(slots),
            "generation_log": ScheduleGenerationLogSerializer(log).data if log else None,
        })
    
class ScheduleGenerationLogListView(APIView):
    """
    GET /scheduling/logs/
    Admin only — view all schedule generation logs.
    """
    permission_classes = [permissions.IsAuthenticated]
 
    def get(self, request):
        if not request.user.is_staff:
            raise PermissionDenied("Only admins can view generation logs.")
 
        logs = ScheduleGenerationLog.objects.select_related(
            "campaign"
        ).order_by("-generated_at")[:100]
 
        return Response(ScheduleGenerationLogSerializer(logs, many=True).data)