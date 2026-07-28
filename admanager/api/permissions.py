from rest_framework.permissions import BasePermission
from security.models import CustomUser


class IsAdManager(BasePermission):
    message = "This endpoint is only available to verified ad manager accounts."

    def has_permission(self, request, view):
        user = request.user
        return (
            user.is_authenticated
            and user.role == CustomUser.UserRole.AD_MANAGER
            and hasattr(user, "ad_manager")
        )