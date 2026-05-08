from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.contrib.auth.password_validation import validate_password

class CustomUserManager(BaseUserManager): 
    def create_user(self, email, password=None, **extra_fields): 
        # Ensure a user cannot sneak these fields in via a registration form
        extra_fields.pop('is_staff', None)
        extra_fields.pop('is_superuser', None)

        if not email:
            raise ValueError("Users must have an email address")            
        
        if not password:
            raise ValueError("Password is required")
        
        email = self.normalize_email(email)
        extra_fields["role"] = self.model.UserRole.AD_MANAGER # force safe default

        validate_password(password)

        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")

        if not password:
            raise ValueError("Password is required")

        email = self.normalize_email(email)

        extra_fields["is_staff"] = True
        extra_fields["is_superuser"] = True
        extra_fields["role"] = self.model.UserRole.ADMIN

        validate_password(password)

        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
class CustomUser(AbstractUser):
    username = None
    email = models.EmailField(unique=True, null=False)

    class UserRole(models.TextChoices):
        AD_MANAGER  = "ad_manager", "Ad Manager"
        ADVERTISER = "advertiser", "Advertiser"
        ADMIN = "admin", "Admin"
    
    role = models.CharField(max_length=20, choices=UserRole.choices)

    objects = CustomUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []