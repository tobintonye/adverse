from django.utils import timezone
from rest_framework import decorators, generics, permissions, response, status, viewsets
from rest_framework.exceptions import PermissionDenied
from admanager.models import Admanager
from ..models import Device
from .serializers import (
    DeviceRegistrationSerializer, DeviceSerializer, HeartbeatSerializer,
    DeviceUpdateSerializer,
    )
from .authentication import DeviceTokenAuthentication
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_401_UNAUTHORIZED
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.exceptions import NotFound

# Return a device owned by this ad-manager user or raise 404/403.
def get_owned_device(user, pk):
    try:
        device = Device.objects.get(pk=pk)
    except Device.DoesNotExist:
        raise NotFound("Device not found.")
    if device.ad_manager.user != user:
        raise PermissionDenied("You do not own this device.")
    return device
 

class DeviceRegisterView(generics.ListCreateAPIView): 
    serializer_class = DeviceRegistrationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Device.objects.filter(ad_manager__user=self.request.user)

    def perform_create(self, serializer):
        if self.request.user.role != "ad_manager":
            raise PermissionDenied("Only ad managers can register devices.")
        ad_manager, _ = Admanager.objects.get_or_create(
            user=self.request.user,
            defaults={"business_name": self.request.user.get_full_name() or self.request.user.username},
        )
        serializer.save(ad_manager=ad_manager, status=Device.Status.PENDING)

# Device Detail  GET /devices/{id}/
class DeviceDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request, pk):
        device = get_owned_device(request.user, pk)
        return Response(DeviceSerializer(device).data)
    
class DeviceHeartbeatView(APIView):
    authentication_classes = [DeviceTokenAuthentication] # only device with active tokens
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = HeartbeatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # device = request.auth 
        device = request.user
        device.mark_heartbeat(**serializer.validated_data)
        return Response({
            "status": "heartbeat acknowledged",
            "device_uid": device.device_uid,
            "last_seen_at": device.last_seen_at,
            "device_status": device.status,
            "firmware_version": device.firmware_version or None,
        }, status=HTTP_200_OK)

class DeviceUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        device = get_owned_device(request.user, pk)
        serializer = DeviceUpdateSerializer(device, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(DeviceSerializer(device).data)
    
class DeviceRotateTokenView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request, pk):
        device = get_owned_device(request.user, pk)
        device.rotate_token()
        device.refresh_from_db() 
        return Response({
                "detail": "Token rotated. Store the new token immediately — it will not be shown again.",
                "new_auth_token": device.auth_token,
                "rotated_at": timezone.now(),
            })