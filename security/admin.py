from django.contrib import admin
from .models import CustomUser

@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = (
        'email', 
        'role', 
        'password_hash_display', 
        'is_staff', 
        'is_superuser', 
        'is_active', 
        'date_joined'
    )
    list_filter = (
        'role', 
        'is_staff', 
        'is_superuser', 
        'is_active'
    )
    search_fields = (
        'email',
    )
    readonly_fields = ('date_joined', 'last_login', 'password_hash_display')
    
    fieldsets = (
        (None, {'fields': ('email', 'role', 'password_hash_display')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important Dates', {'fields': ('last_login', 'date_joined')}),
    )

    @admin.display(description="Password Hash")
    def password_hash_display(self, obj):
        return obj.password
