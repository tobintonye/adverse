from .serializers import AdManagerProfileSerializer, AdManagerCampaignRequestSerializer
from rest_framework.response import Response
from rest_framework import status, permissions, generics
from advertiser.models import Campaign
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from rest_framework.views import APIView

# from ..models import Admanager
# from .permissions import IsOwnerAdManager

class AdManagerCreateView(generics.CreateAPIView):
    serializer_class = AdManagerProfileSerializer
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
        return super().create(request, *args, **kwargs)

class MyAdManagerProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = AdManagerProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user.ad_manager
    
class AdManagerCampaignRequestsListView(generics.ListAPIView):
    serializer_class = AdManagerCampaignRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        ad_manager_profile = self.request.user.ad_manager
        
        # Filter campaigns booking this manager's billboards that have passed global admin checks
        return Campaign.objects.filter(
            campaign_slots__billboard__ad_manager=ad_manager_profile,
            status=Campaign.Status.PENDING_MANAGER_REVIEW
        ).distinct().order_by('-created_at')
    

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