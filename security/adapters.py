from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model
User = get_user_model()

# auto-line social account to existing user with the same email
class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        if sociallogin.is_existing:
            return
        email = sociallogin.user.email
        if not email:
            return
        
        email_verified = any(
            e.email.lower() == email.lower() and e.verified
            for e in sociallogin.email_addresses
        )
        if not email_verified:
            return  # don't auto-link on an unverified email claim
        try:
            existing_user = User.objects.get(email__iexact=email)
            sociallogin.connect(request, existing_user)
        except User.DoesNotExist:
            pass