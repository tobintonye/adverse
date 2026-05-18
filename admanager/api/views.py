from .serializers import AdManagerProfileSerializer
from rest_framework.response import Response
from rest_framework import status, permissions, generics
from ..models import Admanager
from .permissions import IsOwnerAdManager

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