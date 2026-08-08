from .serializers import ( AdManagerProfileSerializer, AdManagerCampaignRequestSerializer, AdManagerProfileWriteSerializer,
    AdManagerVerificationSerializer, AdManagerDashboardSerializer,
    AdManagerCampaignReviewSerializer,
)
from rest_framework.response import Response
from rest_framework import status, permissions, generics
from advertiser.models import Campaign
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied, NotFound
from ..models import Admanager
from security.models import CustomUser
from django.db import transaction
from decimal import Decimal
from payments.models import AdManagerEarning, PayoutRecord
from advertiser.services import approve_campaign_by_manager, reject_campaign
from rest_framework.exceptions import ValidationError as DRFValidationError
from django.core.exceptions import ValidationError as DjangoValidationError
from .permissions import IsAdManager

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

    def create(self, request, *args, **kwargs):
        if request.user.role != CustomUser.UserRole.AD_MANAGER:
            return Response(
                {"error": "This account is not registered as an ad manager."},
                status=status.HTTP_403_FORBIDDEN,
            )
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
    permission_classes = [permissions.IsAuthenticated, IsAdManager]

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
    permission_classes = [permissions.IsAuthenticated, IsAdManager]

    def get(self, request):
        ad_manager = request.user.ad_manager

        total_earnings = AdManagerEarning.objects.filter(
            ad_manager=ad_manager
        ).aggregate(total=__import__("django.db.models", fromlist=["Sum"]).Sum("amount"))["total"] or Decimal("0")
        total_withdrawn = PayoutRecord.objects.filter(
            ad_manager=ad_manager,
            status__in=[PayoutRecord.Status.SUCCESS, PayoutRecord.Status.PENDING],
        ).aggregate(total=__import__("django.db.models", fromlist=["Sum"]).Sum("amount"))["total"] or Decimal("0")

        data = {
            "id": ad_manager.id,
            "business_name": ad_manager.business_name,
            "verification_status": ad_manager.verification_status,
            "is_verified": ad_manager.is_verified,
            "has_bank_account": ad_manager.has_bank_account,
            "commission_rate": ad_manager.commission_rate,
            "total_billboards": ad_manager.billboards.count(),
            "total_campaigns_served": ad_manager.received_campaigns.filter(
                status__in=[Campaign.Status.APPROVED, Campaign.Status.ACTIVE, Campaign.Status.COMPLETED]
            ).count(),
            "total_impressions": 0,  # wire up via PlaybackLog once decided
            "pending_campaigns": ad_manager.pending_review_campaigns.count(),
            "active_campaigns": ad_manager.active_campaigns.count(),
            "total_earnings": total_earnings,
            "available_balance": total_earnings - total_withdrawn,
        }
        serializer = AdManagerDashboardSerializer(data)
        return Response(serializer.data)

class AdManagerBankAccountView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdManager]

    def get(self, request):
        ad_manager = request.user.ad_manager
        subaccount = getattr(ad_manager, "paystack_subaccount", None)
        if not subaccount:
            return Response({"has_bank_account": False})
        return Response({
            "has_bank_account": True,
            "bank_name": subaccount.bank_name,
            "account_number_last4": subaccount.account_number_last4,
            "account_name": subaccount.account_name,
            "is_active": subaccount.is_active,
            "is_verified": subaccount.is_verified,
        })

    def post(self, request):
        from payments.services import create_paystack_subaccount, update_paystack_subaccount_bank_details

        ad_manager = request.user.ad_manager
        if ad_manager.verification_status == Admanager.VerificationStatus.SUSPENDED:
            return Response(
                {"detail": "Suspended ad manager accounts cannot update payout details."},
                status=status.HTTP_403_FORBIDDEN,
            )

        bank_code = str(request.data.get("bank_code", "")).strip()
        account_number = str(request.data.get("account_number", "")).strip()
        business_name = str(request.data.get("business_name", "")).strip()

        if not bank_code:
            return Response({"bank_code": "Please select a bank."}, status=status.HTTP_400_BAD_REQUEST)
        if not account_number.isdigit() or len(account_number) != 10:
            return Response(
                {"account_number": "Account number must be exactly 10 digits."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        subaccount = getattr(ad_manager, "paystack_subaccount", None)

        try:
            if subaccount:
                update_paystack_subaccount_bank_details(
                    subaccount=subaccount, bank_code=bank_code, account_number=account_number,
                    business_name=business_name or None, updated_by=request.user,
                )
            else:
                if not business_name:
                    return Response(
                        {"business_name": "Business name is required."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                create_paystack_subaccount(
                    ad_manager=ad_manager, bank_code=bank_code,
                    account_number=account_number, business_name=business_name,
                )
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"detail": "Bank account details saved. Verification pending."})
    
class AdManagerCampaignRequestsListView(generics.ListAPIView):
    # Lists campaigns pending this manager's review
    serializer_class = AdManagerCampaignRequestSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdManager]

    def get_queryset(self):
        ad_manager_profile = self.request.user.ad_manager
        
        # Filter campaigns booking this manager's billboards that have passed global admin checks
        return Campaign.objects.filter(
            campaign_slots__billboard__ad_manager=ad_manager_profile,
            status=Campaign.Status.PENDING_MANAGER_REVIEW
        ).distinct().order_by('-created_at')
    
class AdManagerCampaignDetailView(APIView):
    # Full detail of a single campaign targeting this manager's billboard.
    permission_classes = [permissions.IsAuthenticated, IsAdManager]
 
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
      - Campaign → APPROVED, approved_at stamped (starts 7-day expiry clock)
      - Media    → FULLY_APPROVED
      - Advertiser notified to pick real campaign dates next
      - Scheduling (TimeSlot generation) does NOT happen here — it only
        happens once the advertiser confirms real dates via
        confirm_campaign_dates(), since dates aren't known at approval time.

    On REJECT:
      - Campaign → REJECTED
      - Media stays at ADMIN_APPROVED (can be reused in a new campaign)
    """
    permission_classes = [permissions.IsAuthenticated, IsAdManager]
 
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
                result = approve_campaign_by_manager(campaign=campaign, manager_user=request.user)
                return Response({
                    "detail": f"Campaign '{campaign.name}' approved. Advertiser can now select campaign dates.",
                    "status": result["status"],
                    "campaign_id": result["campaign_id"],
                })
            else:
                reject_campaign(campaign=campaign, reviewer=request.user, reason=reason)
                return Response({
                    "detail": f"Campaign '{campaign.name}' has been rejected.",
                    "status": campaign.status,
                })
        except DjangoValidationError as e:
            raise DRFValidationError(e.message_dict if hasattr(e, "message_dict") else e.messages)
        
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
    # Admin-only verify, reject, suspend, or reinstate an ad manager account.
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

