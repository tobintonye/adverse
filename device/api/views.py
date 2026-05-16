from django.utils import timezone
from rest_framework import decorators, generics, permissions, response, status, viewsets
from rest_framework.exceptions import PermissionDenied
from admanager.models import Admanager
from ..models import Billboard, PlayerDevice
from .serializers import (
     BillboardSerializer, BillboardWriteSerializer, HeartbeatSerializer,
    PairDeviceSerializer, PlayerDeviceRegistrationSerializer, PlayerDeviceSerializer,
    )
from .authentication import DeviceTokenAuthentication
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_401_UNAUTHORIZED
from rest_framework.permissions import AllowAny, IsAuthenticated
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