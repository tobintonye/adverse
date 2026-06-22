from django.contrib import admin
from django.utils.html import format_html
from django.core.exceptions import ValidationError

from .models import Admanager


@admin.register(Admanager)
class AdmanagerAdmin(admin.ModelAdmin):
    list_display = (
        "business_name",
        "user",
        "business_type",
        "verification_status_badge",
        "is_active",
        "country",
        "city",
        "total_billboards",
        "created_at",
    )
    list_filter = (
        "verification_status",
        "is_active",
        "business_type",
        "country",
    )
    search_fields = (
        "business_name",
        "business_email",
        "business_phone",
        "user__username",
        "user__email",
        "company_registration_number",
        "tax_identification_number",
        "account_number",
        "recipient_code",
    )
    autocomplete_fields = ("user",)
    ordering = ("-created_at",)
    date_hierarchy = "created_at"

    readonly_fields = (
        "id",
        "verified_by",
        "verified_at",
        "suspended_by",
        "suspended_at",
        "total_billboards",
        "total_campaigns_serverd",
        "total_impressions",
        "created_at",
        "updated_at",
        "has_bank_account_display",
    )

    fieldsets = (
        ("Account", {
            "fields": ("id", "user", "is_active")
        }),
        ("Business Details", {
            "fields": (
                "business_name", "business_type",
                "company_registration_number", "tax_identification_number",
                "business_email", "business_phone", "website",
            )
        }),
        ("Location", {
            "fields": ("address", "city", "state", "country")
        }),
        ("Verification", {
            "fields": (
                "verification_status",
                "rejection_reason", "suspension_reason",
                "verified_by", "verified_at",
                "suspended_by", "suspended_at",
            )
        }),
        ("Financials", {
            "fields": (
                "commission_rate",
                "bank_name", "account_number", "account_name",
                "bank_code", "recipient_code", "has_bank_account_display",
            )
        }),
        ("Stats", {
            "fields": ("total_billboards", "total_campaigns_serverd", "total_impressions")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at")
        }),
    )

    actions = ["verify_managers", "reject_managers", "suspend_managers", "reinstate_managers"]

    @admin.display(description="Status")
    def verification_status_badge(self, obj):
        colors = {
            Admanager.VerificationStatus.PENDING: "#d97706",
            Admanager.VerificationStatus.VERIFIED: "#16a34a",
            Admanager.VerificationStatus.REJECTED: "#dc2626",
            Admanager.VerificationStatus.SUSPENDED: "#6b7280",
        }
        color = colors.get(obj.verification_status, "#000")
        return format_html(
            '<span style="color:{};font-weight:600;">{}</span>',
            color,
            obj.get_verification_status_display(),
        )

    @admin.display(description="Bank details complete?", boolean=True)
    def has_bank_account_display(self, obj):
        return obj.has_bank_account

    def _run_action(self, request, queryset, method_name, **kwargs):
        success, failed = 0, []
        for manager in queryset:
            try:
                getattr(manager, method_name)(admin_user=request.user, **kwargs)
                success += 1
            except ValidationError as e:
                failed.append(f"{manager.business_name}: {e.message if hasattr(e, 'message') else e}")
        if success:
            self.message_user(request, f"{success} ad manager(s) updated successfully.")
        for msg in failed:
            self.message_user(request, msg, level="error")

    @admin.action(description="Verify selected ad managers")
    def verify_managers(self, request, queryset):
        success, failed = 0, []
        for manager in queryset:
            try:
                manager.verify(admin_user=request.user)
                success += 1
            except ValidationError as e:
                failed.append(f"{manager.business_name}: {e}")
        if success:
            self.message_user(request, f"{success} ad manager(s) verified.")
        for msg in failed:
            self.message_user(request, msg, level="error")

    @admin.action(description="Reject selected ad managers (default reason: 'Rejected via admin bulk action')")
    def reject_managers(self, request, queryset):
        self._run_action(
            request, queryset, "reject",
            reason="Rejected via admin bulk action"
        )

    @admin.action(description="Suspend selected ad managers (default reason: 'Suspended via admin bulk action')")
    def suspend_managers(self, request, queryset):
        self._run_action(
            request, queryset, "suspend",
            reason="Suspended via admin bulk action"
        )

    @admin.action(description="Reinstate selected ad managers")
    def reinstate_managers(self, request, queryset):
        self._run_action(request, queryset, "reinstate")

"""
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
"""