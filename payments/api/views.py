import json
import logging
 
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
 
from ..models import AdManagerSubaccount, AdManagerEarning, CampaignPayment, PayoutRecord
from .serializers import ( AdManagerEarningSerializer, AdManagerSubaccountSerializer, CampaignPaymentSerializer,
                            InitiateCampaignPaymentSerializer, PayoutRecordSerializer, SubaccountAuditLogSerializer, 
                            SubaccountSetupSerializer, UpdateBankDetailsSerializer
                        )
from ..services import ( create_paystack_subaccount, handle_charge_success, 
                        initiate_campaign_refund, initialize_campaign_payment, update_paystack_subaccount_bank_details, verify_paystack_signature)
 
logger = logging.getLogger(__name__)

# Permissions
class IsAdManager(BasePermission):
    # Request user must have an associated AdManager instance
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and hasattr(request.user, "ad_manager"))
    
class IsAdvertiser(BasePermission):
    # Request user must have an associated Advertiser instance
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and hasattr(request.user, "advertiser"))
 
# Pagination
class BillingPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

class SubaccountSetupView(APIView):
    """
    POST /billing/subaccount/setup/
    Ad manager sets up their Paystack subaccount during onboarding.
    One per ad manager — raises if already exists.
    """
    def post(self, request):
        ad_manager = request.user.ad_manager

        if hasattr(ad_manager, "paystack_subaccount"): 
            return Response({"detail": "A subaccount already exists for this ad manager."}, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = SubaccountSetupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            subaccount = create_paystack_subaccount(
                ad_manager=ad_manager,
                bank_code=serializer.validated_data["bank_code"],
                account_number=serializer.validated_data["account"],
                business_name=serializer.validated_data["business_name"],
            )
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            AdManagerSubaccountSerializer(subaccount).data,
            status=status.HTTP_201_CREATED,
        )
    
class SubaccountDetailView(APIView):
    """
    GET /billing/subaccount/
    Returns the current ad manager's subaccount details (masked account number).
    """
    permission_classes = [IsAuthenticated, IsAdManager]
    def get(self, request):
        if not hasattr(request.user.ad_manager, "paystack_subaccount"):
            return Response({"detail": "No subaccount found. Please complete onboarding."}, status=status.HTTP_404_NOT_FOUND)
        return Response(AdManagerSubaccountSerializer(request.user.ad_manager.paystack_subaccount).data)
    
class SubaccountUpdateBankView(APIView):
    """
    POST /billing/subaccount/update-bank/
    Ad manager updates their bank details.
 
    Calls the service layer which:
    1. Re-verifies the new account via Paystack name enquiry
    2. Updates the subaccount on Paystack's side
    3. Saves only the last 4 digits locally
    4. Clears verified_at so payments are blocked until re-verified
    """

    permission_classes = [IsAuthenticated, IsAdManager]
    
    def post(self, request):
        ad_manager = request.user.ad_manager

        if not hasattr(ad_manager, "paystack_subaccount"):
            return Response({"detail": "No subaccount found."}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = UpdateBankDetailsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            subaccount = update_paystack_subaccount_bank_details(
                subaccount=ad_manager.paystack_subaccount,
                bank_code=serializer.validated_data["bank_code"],
                account_number=serializer.validated_data["account_number"],
                business_name=serializer.validated_data.get("business_name"),
                updated_by=request.user,
            )
        except ValidationError as e:
            return ValidationError({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(AdManagerSubaccountSerializer(subaccount).data,)
    
class SubaccountAuditLogView(APIView):
    """
    GET /billing/subaccount/audit-log/?ad_manager_id=<id>
    Returns the audit log for an ad manager's subaccount.
    Staff only.
    """

    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        if not request.user.is_staff:
            return Response(status=status.HTTP_403_FORBIDDEN)
        
        ad_manager_id = request.query_params.get("ad_manager_id", "").strip()
        if not ad_manager_id:
            return Response({"detail": "ad_manager_id query param required."}, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate that ad_manager_id is a valid integer before hitting the ORM
        try:
            ad_manager_id = int(ad_manager_id)
        except (ValueError, TypeError):
            return Response({"detail": "ad_manager_id must be a valid integer."},status=status.HTTP_400_BAD_REQUEST)
        try:
            subaccount = AdManagerSubaccount.objects.get(ad_manager_id=ad_manager_id)
        except AdManagerSubaccount.DoesNotExist:
            return Response({"detail": "No subaccount found for this ad manager."},status=status.HTTP_404_NOT_FOUND)
        
        logs = subaccount.audit_logs.order_by("-created_at")
        paginator = BillingPagination()
        page = paginator.paginate_queryset(logs, request)
        return paginator.get_paginated_response(
            SubaccountAuditLogSerializer(page, many=True).data
        )
    
# Campaign payment
class InitiateCampaignPaymentView(APIView):
    """
    POST /billing/campaigns/pay/
    Advertiser initiates payment for an approved campaign.
    Returns Paystack authorization_url to redirect the user to.
    """
    permission_classes = [IsAuthenticated, IsAdvertiser]

    def post(self, request):
        serializer = InitiateCampaignPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        campaign_id = serializer.validated_data["campaign_id"]

        try:
            campaign = request.user.advertiser.campaigns.get(id=campaign_id)
        except ObjectDoesNotExist:
            return Response({"detail": "Campaign not found."}, status=status.HTTP_404_NOT_FOUND)
        
        """
            Block if payment already exists and is PENDING or COMPLETED.
            PENDING: an active Paystack checkout is already open.
            COMPLETED: campaign already paid for.
        """
        if hasattr(campaign, "payment") and campaign.payment.status in (CampaignPayment.Status.PENDING, CampaignPayment.Status.COMPLETED):
            return Response({"detail": "A payment for this campaign is already in progress or completed"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            paystack_data = initialize_campaign_payment(campaign)
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response({
            "authorization_url": paystack_data.get("authorization_url"),
            "access_code": paystack_data.get("access_code"),
            "reference": paystack_data.get("reference"),
        })
    
class CampaignPaymentDetailView(APIView):
    """
        GET /billing/campaigns/<campaign_id>/payment/
        Returns the payment record for a campaign.
        Advertiser can only see their own campaign's payment.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, campaign_id):
        try:
            payment = CampaignPayment.objects.select_related("campaign").get(
                campaign_id=campaign_id,
                campaign__advertiser__user=request.user,
            )
        except CampaignPayment.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
 
        return Response(CampaignPaymentSerializer(payment).data)
    
class CampaignRefundView(APIView):
    """
        POST /billing/campaigns/<campaign_id>/refund/
        Initiates a refund for a completed campaign payment.
        Staff only — advertisers cannot self-serve refunds.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, campaign_id):
        if not request.user.is_staff:
            return Response(status=status.HTTP_403_FORBIDDEN)
        
        try:
            payment = CampaignPayment.objects.select_related("campaign").get(campaign_id=campaign_id)
        except CampaignPayment.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        
        try:
            initiate_campaign_refund(payment.campaign, initiated_by=request.user)
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response({"detail": "Refund initiated. Paystack will confirm via webhook."})
    
# Ad Manager Earnings
class AdManagerEarningsView(APIView):
    """
    GET /billing/earnings/
    Returns paginated earning history for the current ad manager.
    """
    permission_classes = [IsAuthenticated, IsAdManager]
 
    def get(self, request):
        earnings = (
            AdManagerEarning.objects
            .filter(ad_manager=request.user.ad_manager)
            .select_related("payment__campaign")
            .order_by("-earned_at")
        )
        paginator = BillingPagination()
        page = paginator.paginate_queryset(earnings, request)
        return paginator.get_paginated_response(
            AdManagerEarningSerializer(page, many=True).data
        )

# Payout History
class PayoutHistoryView(APIView):
    """
    GET /billing/payouts/
    Returns paginated payout history for the current ad manager.
    """
    permission_classes = [IsAuthenticated, IsAdManager]
 
    def get(self, request):
        payouts = (PayoutRecord.objects.filter(ad_manager=request.user.ad_manager).order_by("-created_at"))
        paginator = BillingPagination()
        page = paginator.paginate_queryset(payouts, request)
        return paginator.get_paginated_response(PayoutRecordSerializer(page, many=True).data)
    

# Paystack Webhook
@method_decorator(csrf_exempt, name="dispatch")
class PaystackWebhookView(APIView):
    """
    POST /billing/webhook/paystack/
 
    Single endpoint for all Paystack webhook events.
    Paystack sends all events here — we route by event type.
 
    Security:
    - CSRF exempt (Paystack can't send a CSRF token)
    - Signature verified via X-Paystack-Signature header before any DB work
    - Returns 200 for unknown events (Paystack retries on non-200)
    - Processing errors are logged, not raised (avoids Paystack retry storms)
    """
    authentication_classes = []
    permission_classes = []
 
    def post(self, request):
        # verify signature before anything else
        signature = request.headers.get("X-Paystack-Signature", "")
        try:
            if not verify_paystack_signature(request.body, signature):
                logger.warning("Paystack webhook: invalid signature.")
                return HttpResponse(status=401)
        except ValidationError as e:
            logger.error("Paystack webhook signature check failed: %s", e)
            return HttpResponse(status=500)
 
        #parse payload
        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            logger.error("Paystack webhook: invalid JSON payload.")
            return HttpResponse(status=400)
 
        event = payload.get("event", "")
        logger.info("Paystack webhook received: %s", event)
 
        # route by event type
        try:
            if event == "charge.success":
                # Pass the full payload — handler extracts data internally
                handle_charge_success(payload)
 
            elif event == "charge.dispute.create":
                # Log for manual review — no automated action
                logger.warning(
                    "Paystack dispute raised: dispute_id=%s — manual review required.",
                    payload.get("data", {}).get("id"),
                )
 
            else:
                logger.info(
                    "Paystack webhook: unhandled event type '%s' — ignored.", event
                )
 
        except ValidationError as e:
            # Log but return 200 — prevents Paystack from retrying endlessly
            logger.error("Paystack webhook processing error [%s]: %s", event, e)
 
        except Exception as e:
            logger.exception(
                "Paystack webhook unexpected error [%s]: %s", event, e
            )
 
        # Always return 200 so Paystack does not retry
        return HttpResponse(status=200)
 