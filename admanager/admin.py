from django.contrib import admin
from django.contrib import messages
from .models import Admanager

@admin.register(Admanager)
class AdmanagerAdmin(admin.ModelAdmin):
    list_display = (
        'business_name', 
        'user', 
        'user_password_hash',
        'business_type', 
        'business_email', 
        'business_phone', 
        'verification_status', 
        'is_active', 
        'created_at'
    )
    list_filter = (
        'verification_status', 
        'business_type', 
        'is_active', 
        'state', 
        'country'
    )
    search_fields = (
        'business_name', 
        'business_email', 
        'business_phone', 
        'user__username', 
        'user__email'
    )
    readonly_fields = ('created_at', 'update_at', 'user_password_hash')
    
    actions = ['approve_verification', 'reject_verification', 'suspend_managers']

    @admin.display(description="User Password Hash")
    def user_password_hash(self, obj):
        return obj.user.password

    @admin.action(description="Verify selected Ad Managers")
    def approve_verification(self, request, queryset):
        count = 0
        for manager in queryset:
            if manager.verification_status != Admanager.VerificationStatus.VERIFIED:
                manager.verify(request.user)
                count += 1
        self.message_user(request, f"Successfully verified {count} Ad Manager(s).", messages.SUCCESS)

    @admin.action(description="Reject selected Ad Managers")
    def reject_verification(self, request, queryset):
        updated = queryset.update(
            verification_status=Admanager.VerificationStatus.REJECTED,
            verification_requested=False,
            rejection_reason="Rejected via system administration."
        )
        self.message_user(request, f"Rejected verification requests for {updated} Ad Manager(s).", messages.WARNING)

    @admin.action(description="Suspend selected Ad Managers")
    def suspend_managers(self, request, queryset):
        count = 0
        for manager in queryset:
            manager.suspend()
            count += 1
        self.message_user(request, f"Suspended {count} Ad Manager(s).", messages.SUCCESS)

from .models import WithdrawalRequest

@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(admin.ModelAdmin):
    list_display = ('ad_manager', 'amount', 'status', 'created_at', 'updated_at')
    list_filter = ('status', 'created_at')
    search_fields = ('ad_manager__business_name', 'bank_details')
    readonly_fields = ('created_at', 'updated_at')


from .models import BankAccount

@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ('ad_manager', 'bank_name', 'account_number', 'account_name', 'is_default', 'created_at')
    list_filter = ('is_default',)
    search_fields = ('ad_manager__business_name', 'bank_name', 'account_number', 'account_name')
    readonly_fields = ('created_at',)
