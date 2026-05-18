from rest_framework.permissions import BasePermission


class IsOwnerAdManager(BasePermission):
    """
    Only allow owners of the profile to access/edit it.
    """

    def has_object_permission(self, request, view, obj):
        return obj.user == request.user