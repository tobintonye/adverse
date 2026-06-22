from .serializers import ( AdManagerProfileSerializer, AdManagerCampaignRequestSerializer, AdManagerProfileWriteSerializer,
                            AdManagerBankAccountSerializer, AdManagerVerificationSerializer, AdManagerDashboardSerializer, 
                            AdManagerMediaDetailSerializer, AdManagerCampaignReviewSerializer
                        )
from rest_framework.response import Response
from rest_framework import status, permissions, generics
from advertiser.models import Campaign
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied, NotFound
from ..models import Admanager
from django.db import transaction
from django.db.models import Sum, Count, Q, Value, DecimalField, F
from django.db.models.functions import Coalesce
from rest_framework.exceptions import ValidationError as DRFValidationError
from advertiser.services import approve_campaign_by_manager, reject_campaign
from django.core.exceptions import ValidationError as DjangoValidationError
# from .permissions import IsOwnerAdManager

def get_ad_manager(user):
    try:
        return user.ad_manager
    except Admanager.DoesNotExist:
        raise NotFound("Ad manager profile not found.")

def get_campaign_for_manager(manager, pk):
    """
    Return a campaign that includes this manager's billboard.
    Raises 404 if not found, 403 if this manager has no ownership.
    """
    campaign = get_object_or_404(Campaign.objects.prefetch_related("campaign_slots__billboard__ad_manager"), pk=pk)
    has_ownership = campaign.campaign_slots.filter(billboard__ad_manager=manager).exists()
    if not has_ownership:
        raise PermissionDenied(
            "You do not have permission to manage this campaign."
        )
    return campaign

class AdManagerCreateView(generics.CreateAPIView):
    serializer_class =  AdManagerProfileWriteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        # Prevent duplicate profile creation
        if hasattr(request.user, "ad_manager"):
            return Response(
                {"error": "Profile already exists"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
             ad_manager = serializer.save(user=request.user)

        return Response(
            AdManagerProfileSerializer(ad_manager, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

class AdManagerProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user.ad_manager
    
    def get_serializer_class(self):
        if self.request.method in ["PUT", "PATCH"]:
            return AdManagerProfileWriteSerializer
        return AdManagerProfileSerializer

    def update(self, request, *args, **kwargs):
        ad_manager = self.get_object()

        if ad_manager.verification_status == Admanager.VerificationStatus.SUSPENDED:
            return Response(
                {"detail": "Suspended ad manager accounts cannot update their profile."},
                status=status.HTTP_403_FORBIDDEN,
            )

        partial = kwargs.pop("partial", False)
        serializer = self.get_serializer(ad_manager, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            serializer.save()

        return Response(
            AdManagerProfileSerializer(ad_manager, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

class AdManagerDashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            admanager = Admanager.objects.select_related('user__wallet').annotate(
                pending_campaigns=Count('pending_review_campaigns', distinct=True),
                active_campaigns=Count('active_campaigns', distinct=True),
                total_earnings=Coalesce(
                    Sum('earnings__amount', filter=Q(earnings__is_credited=True)),
                    Value(0.0),
                    output_field=DecimalField()
                ),
                wallet_balance=Coalesce(
                    F('user__wallet__balance'),
                    Value(0.0),
                    output_field=DecimalField()
                )
            ).get(user=request.user)
            
        except Admanager.DoesNotExist:
            return Response({"error": "Admanager profile not found."}, status=404)
        serializer = AdManagerDashboardSerializer(admanager)
        return Response(serializer.data)

class AdManagerBankAccountView(generics.RetrieveUpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AdManagerBankAccountSerializer
    def get_object(self):
        return self.request.user.ad_manager
    
    def update(self, request, *args, **kwargs):
        ad_manager = self.get_object()
        if ad_manager.verification_status == Admanager.VerificationStatus.SUSPENDED:
            return Response(
                {"detail": "Suspended ad manager accounts cannot update payout details."},
                status=status.HTTP_403_FORBIDDEN,
            )
        partial = kwargs.pop("partial", False)
        serializer = self.get_serializer(ad_manager, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            serializer.save()

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )
    
class AdManagerCampaignRequestsListView(generics.ListAPIView):
    # Lists campaigns pending this manager's review
    serializer_class = AdManagerCampaignRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        ad_manager_profile = self.request.user.ad_manager
        
        # Filter campaigns booking this manager's billboards that have passed global admin checks
        return Campaign.objects.filter(
            campaign_slots__billboard__ad_manager=ad_manager_profile,
            status=Campaign.Status.PENDING_MANAGER_REVIEW
        ).distinct().order_by('-created_at')
    
class AdManagerCampaignDetailView(APIView):
    # Full detail of a single campaign targeting this manager's billboard.

    permission_classes = [permissions.IsAuthenticated]
 
    def get(self, request, pk):
        manager  = get_ad_manager(request.user)
        campaign = get_campaign_for_manager(manager, pk)
        return Response(
            AdManagerCampaignRequestSerializer(
                campaign, context={"request": request}
            ).data
        )

class AdManagerCampaignReviewView(APIView):
    """
    POST /admanager/campaigns/<uuid:pk>/review/
 
    Ad manager approves or rejects a campaign in PENDING_MANAGER_REVIEW.
 
    On APPROVE:
      - Campaign → APPROVED
      - Media    → FULLY_APPROVED
      - Payment  → deducted from advertiser wallet, credited to ad manager
      - Schedule → TimeSlots generated for every campaign day
      All of this happens atomically via the service layer.
 
    On REJECT:
      - Campaign → REJECTED
      - Media stays at ADMIN_APPROVED (can be reused in a new campaign)
    """
    permission_classes = [permissions.IsAuthenticated]
 
    def post(self, request, pk):
        manager  = get_ad_manager(request.user)
        campaign = get_campaign_for_manager(manager, pk)
 
        if campaign.status != Campaign.Status.PENDING_MANAGER_REVIEW:
            return Response(
                {"detail": "Only campaigns in 'Pending Manager Review' can be reviewed."},
                status=status.HTTP_400_BAD_REQUEST,
            )
 
        serializer = AdManagerCampaignReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
 
        action = serializer.validated_data["action"]
        reason = serializer.validated_data.get("rejection_reason", "")
 
        try:
            if action == "approve":
                # Goes through the service layer — payment + schedule fires here
                result = approve_campaign_by_manager(
                    campaign=campaign,
                    manager_user=request.user,
                )
                return Response({
                    "detail": f"Campaign '{campaign.name}' approved and deployed live.",
                    "status": campaign.status,
                    "slots_created": result["slots_created"],
                    "slots_skipped": result["slots_skipped"],
                    "payment_total": str(result["payment_total"]),
                    "warning": (
                        f"{result['slots_skipped']} slots skipped due to billboard capacity."
                        if result["slots_skipped"] else None
                    ),
                })
            else:
                reject_campaign(
                    campaign=campaign,
                    reviewer=request.user,
                    reason=reason,
                )
                return Response({
                    "detail": f"Campaign '{campaign.name}' has been rejected.",
                    "status": campaign.status,
                })
 
        except DjangoValidationError as e:
            raise DRFValidationError(
                e.message_dict if hasattr(e, "message_dict") else e.messages
            )
        
# admin ----         
class AdminAdManagerListView(generics.ListAPIView):
    serializer_class = AdManagerProfileSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        queryset = Admanager.objects.select_related("user").order_by("-created_at")

        verification_status = self.request.query_params.get("verification_status")
        if verification_status:
            queryset = queryset.filter(verification_status=verification_status)

        return queryset

class AdminAdManagerVerificationView(APIView):
    # Admin-only — verify, reject, suspend, or reinstate an ad manager account.
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):
        serializer = AdManagerVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action = serializer.validated_data["action"]
        reason = serializer.validated_data.get("reason", "")

        with transaction.atomic():
            ad_manager = get_object_or_404(
                Admanager.objects.select_for_update(),
                pk=pk,
            )

            try:
                if action == "verify":
                    ad_manager.verify(admin_user=request.user)
                elif action == "reject":
                    ad_manager.reject(admin_user=request.user, reason=reason)
                elif action == "suspend":
                    ad_manager.suspend(admin_user=request.user, reason=reason)
                elif action == "reinstate":
                    ad_manager.reinstate(admin_user=request.user)
            except ValidationError as exc:
                return Response(
                    {"detail": exc.messages if hasattr(exc, "messages") else str(exc)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        return Response(
            AdManagerProfileSerializer(ad_manager, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

class AdminAdManagerDetailView(generics.RetrieveAPIView):
    serializer_class = AdManagerProfileSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = Admanager.objects.select_related("user")


class AdManagerApproveCampaignView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        campaign = get_object_or_404(Campaign, pk=pk)
        manager_profile = request.user.ad_manager

        # Verify this campaign actually books this manager's billboards
        has_ownership = campaign.campaign_slots.filter(billboard__ad_manager=manager_profile).exists()
        if not has_ownership:
            return Response({"error": "You do not have permission to approve this campaign request."}, status=status.HTTP_403_FORBIDDEN)
        try: 
            campaign.manager_approve(manager_user=request.user)
            return Response({"message": f"Campaign '{campaign.name}' and its media files have been fully approved and deployed live."},status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({"error": e.message}, status=status.HTTP_400_BAD_REQUEST)           

class AdManagerRejectCampaignView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        campaign = get_object_or_404(Campaign, pk=pk)
        manager_profile = request.user.ad_manager
        reason = request.data.get("rejection_reason", "").strip()

        has_ownership = campaign.campaign_slots.filter(billboard__ad_manager=manager_profile).exists()
        if not has_ownership:
            return Response({"error": "You do not have permission to reject this campaign request."}, status=status.HTTP_403_FORBIDDEN)
        if not reason:
            return Response({"rejection_reason": "A detailed rejection reason is required."},status=status.HTTP_400_BAD_REQUEST)
        try:
            campaign.reject(reviewer=request.user, reason=reason)
            return Response(
                {"message": f"Campaign '{campaign.name}' has been rejected."},
                status=status.HTTP_200_OK
            )
        except ValidationError as e:
            return Response({"error": e.message}, status=status.HTTP_400_BAD_REQUEST)


