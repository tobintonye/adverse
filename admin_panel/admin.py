from django.contrib import admin
from .models import RevenueSetting

@admin.register(RevenueSetting)
class RevenueSettingAdmin(admin.ModelAdmin):
    list_display = ('admin_percentage', 'admanager_percentage', 'updated_at')
