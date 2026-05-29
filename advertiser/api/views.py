from django.shortcuts import render
from rest_framework.views import APIView
from device.models import Billboard
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework import permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from ..models import Advertiser, Media, Campaign
from django.db import transaction
from django.contrib.auth import get_user_model
from .serializers import ( AdvertiserProfileSerializer, AdvertiserProfileWriteSerializer, BillboardPublicSerializer,
                           MediaSerializer, MediaUploadSerializer, MediaReviewSerializer, CampaignSlotSerializer,
                           CampaignSerializer, CampaignWriteSerializer, CampaignPriceEstimateSerializer, 
                           CampaignReviewSerializer
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

def get_owned_campaign(advertiser, pk):
    try: 
        return Campaign.objects.prefetch_related(
            "campaign_slots__billboard"
        ).get(pk=pk, advertiser=advertiser)
    except Campaign.DoesNotExist:
        raise NotFound("Campaign not found.")
    

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
    
    def delete(self, request, pk): 
        advertiser = get_advertiser(request.user)
        media = get_owned_media(advertiser, pk)

        if media.campaigns.filter(
            status__in=[Campaign.Status.ACTIVE, Campaign.Status.APPROVED]
        ).exists():
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
        if not request.user.is_staff or request.user.is_superuser:
            raise PermissionDenied("Only admins can review media.")
        try:
            media = Media.objects.get(pk=pk)
        except Media.DoesNotExist:
            raise NotFound("Media not found.")

        serializer = MediaReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action = serializer.validated_data["action"]
        reason = serializer.validated_data.get("rejection_reason", "")

        if action == "approve":
            media.approve(reviewer=request.user)
        else:
            media.reject(reviewer=request.user, reason=reason)
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
        serializer = CampaignWriteSerializer(
            data=request.data,
            context={"advertiser": advertiser},
        )
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
        serializer = CampaignWriteSerializer(campaign, data=request.data, partial=True)
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
        except  ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

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
        except  ValidationError as e:
            return Response({"detail": e.message if hasattr(e, 'message') else str(e)}, status=400)
        return Response({"detail": "Campaign cancelled successfully.", "status": campaign.status})
    
class CampaignReviewView(APIView):
    """
    Ad manager or admin reviews a submitted campaign.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        has_manager_role = getattr(request.user, "role", None) == "ad_manager" or "admin"

        if not request.user.is_staff or request.user.superuser and not has_manager_role:
            raise PermissionDenied("Only admins or ad managers can review campaigns.")
        
        try:
            campaign = Campaign.objects.prefetch_related("campaign_slots__billboard__ad_manager").get(pk=pk)
        except Campaign.DoesNotExist:
            raise NotFound("Campaign not found.")
        
        # Ad manager restriction verification loop
        if not request.user.is_staff or request.user.ad_manager:
            owns_billboard = campaign.campaign_slots.filter(
                billboard__ad_manager__user=request.user
            ).exists()
            if not owns_billboard:
                raise PermissionDenied("You can only review campaigns that target your billboards.") 
        if campaign.status != Campaign.Status.PENDING_APPROVAL:
            return Response({"detail": "Only campaigns pending approval can be reviewed."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = CampaignReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action = serializer.validated_data["action"]
        reason = serializer.validated_data.get("rejection_reason", "")
        with transaction.atomic():
            if action == "approve": 
                campaign.approve(reviewer=request.user)
            else:
                campaign.reject(reviewer=request.user, reason=reason)

            return Response(CampaignSerializer(campaign).data)

class CampaignPriceEstimateView(APIView):
    # returns lives price breakdown without saving anything 

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request): 
        serializer = CampaignPriceEstimateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        start = serializer.validated_data["c"]
        end = serializer.validated_data["end_date"]
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
                billboard = Billboard.objects.get(pk=billboard_id)
            except (Billboard.DoesNotExist, ValidationError):
                continue

            line_total = billboard.price_per_slot * slots_per_day * duration_days
            total += line_total
            breakdown.append({
                "billboard_id": str(billboard.id),
                "billboard_name": billboard.name,
                "location": billboard.location_name,
                "price_per_slot": billboard.price_per_slot,
                "slots_per_day": slots_per_day,
                "duration_days": duration_days,
                "line_total": line_total,
            })
 
        return Response({
            "duration_days": duration_days,
            "estimated_total": total,
            "breakdown": breakdown,
        })