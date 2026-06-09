from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView 
from ...device.models import Billboard
from ...advertiser.models import Campaign
from ..models import ( BillboardCapacity, ScheduleGenerationLog, TimeSlot, check_capacity, 
                    generate_schedule, get_playlist_for_billboard,
)
from .serializers import ( BillboardCapacitySerializer, CapacityCheckSerializer, ScheduleGenerationLogSerializer,
                           TimeSlotSerializer,
                        )
from datetime import date as date_type
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
            "playlist":TimeSlotSerializer(slots, many=True).data
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
        if capacity.max_slots_per_day == 0:
            capacity.recalculate()

        available_today = capacity.available_slots_on(timezone.now().date())

        return Response({
            **BillboardCapacitySerializer(capacity).data,
            "available_today": available_today,
        })
  
class BillboardCapacityRecalculateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        if not request.user.is_staff or request.user.ad_manager:
            raise PermissionDenied("Only admins or ad managers can recalculate capacity.")
        try: 
            billboard = Billboard.objects.get(pk=pk)
        except Billboard.DoesNotExist:
            raise NotFound("Billboard not found.")
        
        slot_duration = int(request.data.get("slot_duration_seconds", 30))
        capacity, _ = BillboardCapacity.objects.get_or_create(billboard=billboard)
        new_max = capacity.recalculate(slot_duration_seconds=slot_duration)

        return Response({
            "detail": "Capacity recalculated.",
            "max_slots_per_day":  new_max,
            "slot_duration_seconds": slot_duration,
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
        TimeSlot.objects.filter(campaign.campaign).delete()
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
        ).values("billboard__name", "date").annotate(slot_count=models.Count("id")).order_by("date", "billboard__name")

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