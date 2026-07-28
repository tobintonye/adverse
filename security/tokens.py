from django.contrib.auth.tokens import PasswordResetTokenGenerator

class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        # differs from the password-reset hash by not including password,
        # and ties it to is_active so it dies once the account is verified
        return f"{user.pk}{user.is_active}{timestamp}"

email_verification_token = EmailVerificationTokenGenerator()