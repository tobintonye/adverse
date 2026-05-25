from django.shortcuts import render
from rest_framework.views import APIView
from device.models import Billboard
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework import permissions, status
from ..models import Advertiser
from django.contrib.auth import get_user_model
from .serializers import ( AdvertiserProfileSerializer, AdvertiserProfileWriteSerializer,BillboardPublicSerializer)

User = get_user_model()

# Get advertiser profile or raise a clean 404
def get_advertiser(user):
    try:
        return Advertiser.objects.get(user=user)
    except Advertiser.DoesNotExist:
        raise NotFound(
            "Advertiser profile not found. "
            "Complete your profile setup at POST /advertiser/profile/."
        )
    
def require_verified(advertiser):
    if not advertiser.is_verified:
        raise PermissionDenied(
            "Your account is pending verification."
            "An admin will review and verify your account before you can submit campaigns."
        )
    
class AdvertiserProfileView(APIView):
    # GET, POST, PATCH - /advertiser/profile/ 
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        advertiser = get_advertiser(request.user)
        return Response(AdvertiserProfileSerializer(advertiser).data)
        
    def post(self, request): 
        if Advertiser.objects.filter(user=request.user).exists():
            return Response(
                {"detail": "Profile already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = AdvertiserProfileWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        advertiser = serializer.save(user=request.user)
        return Response(
            AdvertiserProfileSerializer(advertiser).data,
            status=status.HTTP_201_CREATED,
        )
    
    def patch(self, request):
        advertiser = get_advertiser(request.user)
        serializer = AdvertiserProfileWriteSerializer(
            advertiser, 
            data = request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(AdvertiserProfileSerializer(advertiser).data)
