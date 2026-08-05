import hmac
from rest_framework import authentication, exceptions
from ..models import PlayerDevice

class DeviceTokenAuthentication(authentication.BaseAuthentication):
    keyword = "DeviceToken"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode("utf-8")
        if not header or not header.startswith(f"{self.keyword} "):
            return None
        token = header.split(" ", 1)[1].strip()
        if not token:
            raise exceptions.AuthenticationFailed("No device token provided.")
        try:
            # player = PlayerDevice.objects.get(auth_token=token)
            player = PlayerDevice.objects.select_related("billboard").get(auth_token=token)
        except PlayerDevice.DoesNotExist as exc:
            raise exceptions.AuthenticationFailed("Invalid device token.") from exc
        
        if player.status == PlayerDevice.Status.DISABLED:
            raise exceptions.AuthenticationFailed("Device is disabled.")
        # Constant-time re-check even after the DB lookup succeeds — matches
        if not hmac.compare_digest(player.auth_token, token):
            raise exceptions.AuthenticationFailed("Invalid device token.")
        if player.status == PlayerDevice.Status.DISABLED:
            raise exceptions.AuthenticationFailed("Device is disabled.")

        return (player, token)
        # return (AnonymousUser(), device) to be used in prod