from django.utils import timezone
from rest_framework import  permissions, status
from rest_framework.exceptions import PermissionDenied, NotFound
from admanager.models import Admanager
from scheduling.models import TimeSlot
from ..models import Billboard, PlayerDevice, PlaybackLog
from .serializers import (
     BillboardSerializer, BillboardWriteSerializer, HeartbeatSerializer,
    PairDeviceSerializer, PlayerDeviceRegistrationSerializer, PlayerDeviceSerializer,
    DeviceMetricSerializer, BulkPlaybackLogSerializer, PlaybackLogSerializer
    )
from .authentication import DeviceTokenAuthentication
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_401_UNAUTHORIZED
from rest_framework.permissions import AllowAny
from rest_framework.exceptions import NotFound

def get_ad_manager(user):
    # Return or create the Admanager profile for this user.
    ad_manager, _ = Admanager.objects.get_or_create(
        user=user,
        defaults={"business_name": user.get_full_name() or user.username},
    )
    return ad_manager

# Return a device owned by this ad-manager user or raise 404/403.
def get_owned_billboard(user, pk):
    try:
        billboard = Billboard.objects.get(pk=pk)
    except Billboard.DoesNotExist:
        raise NotFound("Billboard not found.")
    if billboard.ad_manager.user != user:
        raise PermissionDenied("You do not own this device.")
    return billboard
 
def get_owned_player(user, pk):
    try:
        player = PlayerDevice.objects.select_related("billboard").get(pk=pk)
    except PlayerDevice.DoesNotExist:
        raise NotFound("Player device not found.")
    # ownership is through the billboard or directly through ad_manager
    if player.billboard and player.billboard.ad_manager.user != user:
        raise PermissionDenied("You do not own this device.")
    return player

# billboard endpoints
class BillboardListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request): 
        qs = Billboard.objects.filter(ad_manager__user=request.user).order_by("-created_at")
        return Response(BillboardSerializer(qs, many=True).data)

    def post(self, request):
        if request.user.role != "ad_manager":
            raise PermissionDenied("Only ad managers can register billboards.")
        serializer = BillboardWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ad_manager = get_ad_manager(request.user)
        billboard = serializer.save(ad_manager=ad_manager)
        return Response(BillboardSerializer(billboard).data, status=status.HTTP_201_CREATED)

# GET /billboards/{id}
class BillboardDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, pk):
        billboard = get_owned_billboard(request.user, pk)
        return Response(BillboardSerializer(billboard).data)


# PATCH /billboards/{id}/
class BillboardUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def patch(self, request, pk):
        billboard = get_owned_billboard(request.user, pk)
        serializer = BillboardWriteSerializer(billboard, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(BillboardSerializer(billboard).data)
    
class BillboardDeleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def delete(self, request, pk):
        billboard = get_owned_billboard(request.user, pk)
        if billboard.is_paired:
            return Response(
                {"detail": "Cannot delete a billboard with an active device paired. Disable the device first."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        billboard.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

# PlayerDevice endpoints  (JWT auth — dashboard / admin)
class PlayerDeviceListCreateView(APIView):
    """
        GET  /players/ — list all player devices owned by this ad manager
        POST /players/ — register a new player device (generates pairing_code + auth_token)
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = (PlayerDevice.objects.filter(billboard__ad_manager__user=request.user).select_related("billboard").order_by("-created_at"))
        return Response(PlayerDeviceSerializer(qs, many=True).data)
    
    def post(self, request):
        if request.user.role != "ad_manager":
            raise PermissionDenied("Only ad managers can register player devices.")
        device_uid = request.data.get("device_uid")
        if not device_uid:
            return Response({"detail": "device_uid is required."}, status=status.HTTP_400_BAD_REQUEST)
        player = PlayerDevice.objects.create(device_uid=device_uid)
        return Response(PlayerDeviceRegistrationSerializer(player).data, status=status.HTTP_201_CREATED)
    
class PlayerDeviceDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, pk):
        player = get_owned_player(request.user, pk)
        return Response(PlayerDeviceSerializer(player).data)
    
class PairDeviceView(APIView):
    """
    POST /players/pair/
    Ad manager submits { pairing_code, billboard_id } to link a device to a screen.
    The Android box displays its pairing_code; the admin enters it in the dashboard.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = PairDeviceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

    # Ensure the billboard belongs to this ad manager
        billboard_id = serializer.validated_data["billboard_id"]
        billboard = get_owned_billboard(request.user, billboard_id)
        player = serializer.save()
        return Response(
            {
                "detail": "Device paired successfully.",
                "device_uid": player.device_uid,
                "billboard": billboard.name,
                "status": player.status,
            }
        )
    
class PlayerDeviceDisableView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk): 
        player = get_owned_player(request.user, pk)
        if player.status == PlayerDevice.Status.DISABLED:
            return Response({"detail": "Device is already disabled."}, status=status.HTTP_400_BAD_REQUEST)
        player.disable()
        return Response({
            "detail": "Device disabled.",
            "device_uid": player.device_uid,
            "status": player.status,
        })
    
class PlayerDeviceRotateTokenView(APIView):
    permission_classes = [permissions.IsAuthenticated]
 
    def post(self, request, pk):
        player = get_owned_player(request.user, pk)
        player.rotate_token()
        return Response({
            "detail": "Token rotated. Store the new token immediately — it will not be shown again.",
            "new_auth_token": player.auth_token,
            "rotated_at": timezone.now(),
        })
    
#  These are called by the Android box or any media player, not the dashboard.
class PlayerHeartbeatView(APIView):
    """
        API endpoint for the physical billboard hardware (Android box) to check-in.
        
        Purpose:
        - Verifies the device's secure token (authenticates the hardware).
        - Updates the device's status to 'ACTIVE' and refreshes 'last_seen_at'.
        - Logs current telemetry data (e.g., firmware version, storage, current ad playing).
        
        Frequency: 
        - Called automatically by the Player App every 2–3 minutes via the internet.
        - If a device stops calling this, it will be marked 'OFFLINE' on the dashboard.
    """
    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = HeartbeatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        player = request.user
        player.mark_heartbeat(**serializer.validated_data)
        return Response({
            "status": "heartbeat acknowledged",
            "device_uid": player.device_uid,
            "last_seen_at": player.last_seen_at,
            "device_status": player.status,
            "firmware_version": player.firmware_version or None,
            "billboard": player.billboard.name if player.billboard_id else None,
        })
    
class PlayerScheduleView(APIView):
    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        player = request.user
        if not player.is_paired:
            return Response(
                {"detail": "Device is not paired to a billboard yet."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from scheduling.models import get_playlist_for_billboard
        from scheduling.api.serializers import TimeSlotSerializer

        slots = get_playlist_for_billboard(player.billboard)
        return Response({
            "device_uid": player.device_uid,
            "billboard": player.billboard.name,
            "schedule": TimeSlotSerializer(slots, many=True).data,
            "fetched_at": timezone.now(),
        })
    
class PlayerPlaybackView(APIView):
    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = PlaybackLogSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        player = request.user
        data = serializer.validated_data

        time_slot = None
        time_slot_id = data.pop("time_slot_id", None)
        if time_slot_id:
            time_slot = TimeSlot.objects.filter(
                id=time_slot_id, billboard=player.billboard
            ).first()

        log = serializer.save(player=player, time_slot=time_slot)
        return Response(
            {
                "detail": "Playback recorded.",
                "log_id": log.id,
                "media_id": str(log.media_id),
                "completed": log.completed,
            },
            status=status.HTTP_201_CREATED,
        )


class PlayerPlaybackBulkView(APIView):
    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = BulkPlaybackLogSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        player = request.user
        logs_data = serializer.validated_data["logs"]
        created_logs, skipped = [], 0

        for entry in logs_data:
            time_slot = None
            if player.billboard_id:
                time_slot = TimeSlot.objects.filter(
                    billboard=player.billboard,
                    date=entry["started_at"].date(),
                    is_active=True,
                    campaign_slot__campaign__media_id=entry["media_id"],
                ).first()

            log, created = PlaybackLog.objects.get_or_create(
                player=player,
                media_id=entry["media_id"],
                started_at=entry["started_at"],
                defaults={
                    "duration_seconds": entry["duration_seconds"],
                    "completed": entry.get("completed", False),
                    "time_slot": time_slot,
                },
            )
            if created:
                created_logs.append(log)
            else:
                skipped += 1

        return Response(
            {
                "detail": "Bulk playback flush complete.",
                "received": len(logs_data),
                "created": len(created_logs),
                "skipped_duplicates": skipped,
            },
            status=status.HTTP_207_MULTI_STATUS,
        )

class PlayerMetricsView(APIView):
    authentication_classes = [DeviceTokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = DeviceMetricSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        metric = serializer.save(player=request.user)
        return Response(
            {"detail": "Metrics recorded.", "recorded_at": metric.recorded_at},
            status=status.HTTP_201_CREATED,
        )

# billboard self-registration
class PlayerSelfRegisterView(APIView):
    """
        POST /players/register/
        Called by the Android box on first boot with its hardware ID.
        Idempotent — safe to call again after reboot.
        Returns the pairing_code the box should render on screen.
    """
    permission_classes = [AllowAny]
     
    def post(self, request):
        device_uid = request.data.get("device_uid", "").strip()
        if not device_uid:
            return Response({"detail": "device_uid is required."}, status=status.HTTP_400_BAD_REQUEST)
        player, created = PlayerDevice.objects.get_or_create(device_uid=device_uid)
        return Response({
            "pairing_code": player.pairing_code, # rendered on the screen
            "device_uid": player.device_uid,
            "status": player.status,
            "is_paired": player.is_paired,
        },  status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,)

class PlayerPairingStatusView(APIView):
    """
    Polled by the Android box (every 10s) until is_paired is true.
    Returns auth_token exactly once — after that token_claimed_at is set
    and the token is never returned here again.
    """

    permission_classes = [AllowAny]

    def get(self, request): 
        device_uid = request.query_params.get("device_uid", "").strip()
        if not device_uid:
            return Response({"detail": "device_uid query param is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            player = PlayerDevice.objects.select_related("billboard").get(device_uid=device_uid)
        except PlayerDevice.DoesNotExist:
            return Response({"detail": "Device not found."}, status=status.HTTP_404_NOT_FOUND)
        if not player.is_paired:
            return Response({
                "is_paired": False,
                "status": player.status,
                "auth_token": None,
                "billboard": None,
            })
        # Paired — return auth_token only if it hasn't been claimed yet
        unclaimed = player.token_claimed_at is None
        auth_token = player.auth_token if unclaimed else None

        if unclaimed:
            player.claim_token() 
        
        return Response({
            "is_paired": True,
            "status": player.status,
            "auth_token": auth_token,
            "billboard": {
                "id": str(player.billboard.id),
                "name": player.billboard.name,
                "location_name": player.billboard.location_name,
                "resolution": player.billboard.resolution,
                "operating_hours_start": player.billboard.operating_hours_start,
                "operating_hours_end": player.billboard.operating_hours_end,
            },
        })