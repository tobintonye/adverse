from django.shortcuts import render
from rest_framework.views import APIView
from device.models import Billboard
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework import permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from ..models import Advertiser, Media, Campaign
from django.db import transaction
from django.contrib.auth import get_user_model
from security.models import CustomUser
from .serializers import ( AdvertiserProfileSerializer, AdvertiserProfileWriteSerializer, BillboardPublicSerializer,
                           MediaSerializer, MediaUploadSerializer, MediaReviewSerializer,
                           CampaignSerializer, CampaignWriteSerializer, CampaignPriceEstimateSerializer, 
                           CampaignReviewSerializer
                          )
from decimal import Decimal
from  ..services import (approve_campaign_by_manager, reject_campaign,admin_forward_campaign,)

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
        raise NotFound("Media not found.")  

def get_owned_campaign(advertiser, pk):
    try:
        return Campaign.objects.prefetch_related("campaign_slots__billboard").get(pk=pk, advertiser=advertiser)
    except Campaign.DoesNotExist:
        raise NotFound("Campaign not found.")
    

class AdvertiserProfileView(APIView):
    # GET, POST, PATCH - /advertiser/profile/ 
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        advertiser = get_advertiser(request.user)
        return Response(AdvertiserProfileSerializer(advertiser).data)
        
    def post(self, request): 
        if request.user.role != CustomUser.UserRole.ADVERTISER:
            return Response(
                {"detail": "This account is not registered as an advertiser."},
                    status=status.HTTP_403_FORBIDDEN,
            )
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
        qs = Billboard.bookable().order_by("price_per_slot")

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
            billboard = Billboard.bookable().get(pk=pk)
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
        media = get_owned_media(advertiser, pk)
        return Response(MediaSerializer(media).data)
    
    def delete(self, request, pk): 
        advertiser = get_advertiser(request.user)
        media = get_owned_media(advertiser, pk)

        if media.campaigns.filter(status__in=[Campaign.Status.ACTIVE, Campaign.Status.APPROVED]).exists():
            return Response({"detail": "Cannot delete media used in an active or approved campaign."}, status=status.HTTP_400_BAD_REQUEST)
        media.file.delete(save=False)
        media.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    
class MediaReviewView(APIView):
    """    
    Admin only — approves or rejects a media submission.
    Ad managers can also review media that will run on their billboards.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        if not (request.user.is_staff or request.user.is_superuser):
            raise PermissionDenied("Only admins can review media.")
 
        try:
            media = Media.objects.get(pk=pk)
        except Media.DoesNotExist:
            raise NotFound("Media not found.")
 
        serializer = MediaReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data["action"]
        reason = serializer.validated_data.get("rejection_reason", "")

        try:
            if action == "approve":
                media.approve(admin_user=request.user)
            else:
                media.reject(reviewer=request.user, reason=reason)
        except DjangoValidationError as e:
            raise DRFValidationError(e.message_dict if hasattr(e, "message_dict") else e.messages)

        return Response(MediaSerializer(media).data)

class CampaignListCreateView(APIView):
    # GET, POST 
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request): 
        advertiser = get_advertiser(request.user)
        status_filter = request.query_params.get("status")
        qs = Campaign.objects.filter(advertiser=advertiser).prefetch_related("campaign_slots__billboard").order_by("-created_at")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return Response(CampaignSerializer(qs, many=True).data)
    
    def post(self, request):
        advertiser = get_advertiser(request.user)
        serializer = CampaignWriteSerializer(data=request.data, context={"advertiser": advertiser},)
        serializer.is_valid(raise_exception=True)
        campaign = serializer.save()
        return Response(CampaignSerializer(campaign).data, status=status.HTTP_201_CREATED)
    
class CampaignDetailView(APIView):
    # GET, PATCH, DELETE
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        advertiser = get_advertiser(request.user)
        campaign = get_owned_campaign(advertiser, pk)
        return Response(CampaignSerializer(campaign).data)
    
    def patch(self, request, pk):
        advertiser = get_advertiser(request.user)
        campaign = get_owned_campaign(advertiser, pk)

        if campaign.status not in [Campaign.Status.DRAFT, Campaign.Status.REJECTED]: 
            return Response({"detail": "Only draft or rejected campaigns can be edited."}, status=status.HTTP_400_BAD_REQUEST)
        serializer = CampaignWriteSerializer(campaign, data=request.data, partial=True, context={"advertiser": advertiser})
        serializer.is_valid(raise_exception=True)
        campaign = serializer.save()
        return Response(CampaignSerializer(campaign).data)
        
    def delete(self, request, pk): 
        advertiser = get_advertiser(request.user)
        campaign = get_owned_campaign(advertiser, pk)
        deletable = [Campaign.Status.DRAFT, Campaign.Status.REJECTED, Campaign.Status.CANCELLED]
        if campaign.status not in deletable:
            return Response({ "detail": "Only draft, rejected, or cancelled campaigns can be deleted."})
        campaign.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class CampaignSubmitView(APIView):
    """
        POST /advertiser/campaigns/<uuid:pk>/submit/
        Moves draft → pending_approval.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        advertiser = get_advertiser(request.user)
        require_verified(advertiser)
        campaign = get_owned_campaign(advertiser, pk)
        try:
            campaign.submit_for_approval()
        except DjangoValidationError as e:
            raise DRFValidationError(e.message_dict if hasattr(e, "message_dict") else e.messages)
        return Response({
            "detail": "Campaign submitted for approval successfully.",
            "campaign_id": str(campaign.id),
            "status": campaign.status,
        })
    
class CampaignCancelView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        advertiser = get_advertiser(request.user)
        campaign = get_owned_campaign(advertiser, pk)
        try:
            campaign.cancel()
        except DjangoValidationError as e:
            raise DRFValidationError(e.message_dict if hasattr(e, "message_dict") else e.messages)
        return Response({"detail": "Campaign cancelled successfully.", "status": campaign.status})
    
class CampaignAdminForwardView(APIView):
    """
    POST /advertiser/campaigns/<uuid:pk>/admin-review/

    Admin-only: PENDING_ADMIN_REVIEW → PENDING_MANAGER_REVIEW (or reject).

    Ad-manager approval/rejection is NOT handled here it lives at
    admanager's own AdManagerCampaignReviewView.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        user = request.user
        if not (user.is_staff or user.is_superuser):
            raise PermissionDenied("Only admins can perform this review.")

        try:
            campaign = Campaign.objects.get(pk=pk)
        except Campaign.DoesNotExist:
            raise NotFound("Campaign not found.")

        if campaign.status != Campaign.Status.PENDING_ADMIN_REVIEW:
            return Response(
                {"detail": "Only campaigns pending admin review can be forwarded here."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = CampaignReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data["action"]
        reason = serializer.validated_data.get("rejection_reason", "")

        try:
            with transaction.atomic():
                if action == "reject":
                    reject_campaign(campaign, reviewer=user, reason=reason)
                else:
                    admin_forward_campaign(campaign, admin_user=user)
        except DjangoValidationError as e:
            raise DRFValidationError(e.message_dict if hasattr(e, "message_dict") else e.messages)

        return Response(CampaignSerializer(campaign).data)

class CampaignPriceEstimateView(APIView):
    # Returns a live price breakdown without saving anything.
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = CampaignPriceEstimateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        start = serializer.validated_data["start_date"]
        end = serializer.validated_data["end_date"]
        daily_start = serializer.validated_data.get("daily_start_time")
        daily_end = serializer.validated_data.get("daily_end_time")
        duration_days = (end - start).days + 1
        slots = serializer.validated_data["slots"]

        total = Decimal("0")
        breakdown = []

        for slot in slots:
            billboard_id = slot.get("billboard")
            try:
                slots_per_day = int(slot.get("slots_per_day", 1))
            except (ValueError, TypeError):
                slots_per_day = 1
            try:
                billboard = Billboard.bookable().get(pk=billboard_id)
            except (Billboard.DoesNotExist, DjangoValidationError):
                continue

            if billboard.charge_unit == Billboard.ChargeUnit.DAILY:
                line_total = billboard.price_per_slot * duration_days
            elif billboard.charge_unit == Billboard.ChargeUnit.HOURLY:
                if daily_start and daily_end:
                    from datetime import datetime, date
                    dt1 = datetime.combine(date.min, daily_start)
                    dt2 = datetime.combine(date.min, daily_end)
                    diff_hours = Decimal(str((dt2 - dt1).total_seconds() / 3600.0))
                    line_total = billboard.price_per_slot * diff_hours * duration_days
                else:
                    line_total = billboard.price_per_slot * duration_days
            else:  # SLOT
                line_total = billboard.price_per_slot * slots_per_day * duration_days

            total += line_total
            breakdown.append({
                "billboard_id": str(billboard.id),
                "billboard_name": billboard.name,
                "location": billboard.location_name,
                "price_per_slot": billboard.price_per_slot,
                "charge_unit": billboard.charge_unit,
                "slots_per_day": slots_per_day,
                "duration_days": duration_days,
                "line_total": line_total,
            })

        return Response({
            "duration_days": duration_days,
            "estimated_total": total,
            "breakdown": breakdown,
        })