from django.shortcuts import render
from rest_framework.views import APIView
from device.models import Billboard
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework import permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from ..models import Advertiser, Media
from django.contrib.auth import get_user_model
from .serializers import ( AdvertiserProfileSerializer, AdvertiserProfileWriteSerializer, BillboardPublicSerializer,
                           MediaSerializer, MediaUploadSerializer,
                          )
from decimal import Decimal

User = get_user_model()

# Get advertiser profile or raise a clean 404
def get_advertiser(user):
    try:
        return Advertiser.objects.get(user=user)
    except Advertiser.DoesNotExist:
        raise NotFound(
            "Advertiser profile not found. "
            "Complete your profile setup at /advertiser/profile/."
        )
    
def require_verified(advertiser):
    if not advertiser.is_verified:
        raise PermissionDenied(
            "Your account is pending verification."
            "An admin will review and verify your account before you can submit campaigns."
        )
    
def get_owned_media(advertiser, pk):
    try:
        return Media.objects.get(pk=pk, advertiser=advertiser)  
    except Media.DoesNotExist:
        return NotFound("Media not found.")
    
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


class BillboardBrowseView(APIView):
    '''
    browse available billboards to book for campaigns.
    Filters: ?screen_type=led  ?location=Lagos  ?max_price=5000
    '''
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = Billboard.objects.filter(
            availability = Billboard.Availability.AVAILABLE
        ).order_by("price_per_slot")

        screen_type = request.query_params.get("screen_type")
        location = request.query_params.get("location")
        max_price = request.query_params.get("max_price")

        if screen_type:
            qs = qs.filter(screen_type=screen_type)
        if location:
            qs = qs.filter(location_name__icontains=location)
        if max_price:
            try:
                qs = qs.filter(price_per_slot__lte=Decimal(max_price))
            except Exception:
                pass
 
        return Response(BillboardPublicSerializer(qs, many=True).data)
    
class BillboardBrowseDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]
 
    def get(self, request, pk):
        try:
            billboard = Billboard.objects.get(
                pk=pk, availability=Billboard.Availability.AVAILABLE
            )
        except Billboard.DoesNotExist:
            raise NotFound("Billboard not found or not available.")
        return Response(BillboardPublicSerializer(billboard).data)
    
class MediaListUploadView(APIView):
    # Filters: ?status=pending|approved|rejected
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [permissions.IsAuthenticated]

    # get list of uploaded media by an advertiser 
    def get(self, request): 
        advertiser = get_advertiser(request.user)
        status_filter = request.query_params.get("status")
        qs = Media.objects.filter(advertiser=advertiser).order_by("-created_at")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return Response(MediaSerializer(qs, many=True).data)
    
    def post(self, request):
        advertiser = get_advertiser(request.user)
        serializer = MediaUploadSerializer(data=request.data, context={"advertiser":advertiser})
        serializer.is_valid(raise_exception=True)
        media = serializer.save()
        return Response(MediaSerializer(media).data, status=status.HTTP_201_CREATED)
    
class MediaDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        advertiser = get_advertiser(request.user)
        media = (advertiser, pk)
        return Response(MediaSerializer(media).data)
    