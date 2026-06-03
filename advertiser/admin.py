from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from django.db import transaction
from django.contrib import messages
from .models import Media, Campaign, CampaignSlot, Advertiser
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model

User = get_user_model()

class CampaignSlotInline(admin.TabularInline):
    model = CampaignSlot
    extra = 0
    readonly_fields = ("slot_price",)
    can_delete = True

@admin.register(Advertiser)
class AdvertiserAdmin(admin.ModelAdmin):
    list_display = ("business_name", "contact_person", "business_category", "is_verified", "verified_at_display", "verified_by")
    list_filter = ("is_verified", "business_category", "created_at")
    search_fields = ("business_name", "user__username", "user__email", "first_name", "last_name")
    actions = ["verify_advertisers"]

    fieldsets = (
        (_("Profile Details"), {"fields": ("user", ("first_name", "last_name"), "business_name", "business_category")}),
        (_("Contact & Digital"), {"fields": ("contact_phone", "website", "address")}),
        (_("Verification Status"), {"fields": ("is_verified", "verified_at", "verified_by")}),
    )
    # readonly_fields = ("verified_at", "verified_by")
    
    @admin.display(description="Contact Person")
    def contact_person(self, obj):
        if obj.first_name or obj.last_name:
            return f"{obj.first_name or ''} {obj.last_name or ''}".strip()
        return format_html('<a href="mailto:{0}">{0}</a>', obj.user.email)
    
    @admin.display(description="Verified At")
    def verified_at_display(self, obj):
         return obj.verified_at.strftime("%Y-%m-%d %H:%M") if obj.verified_at else "-"
    
    @admin.action(description="Verify selected advertisers")
    def verify_advertisers(self, request, queryset):
        updated = 0
        # ensure all updates succeed or fail together
        with transaction.atomic():
            for advertiser in queryset.filter(is_verified=False):
                advertiser.verify(admin_user=request.user)
                updated += 1
        self.message_user(request, f"{updated} advertisers successfully verified.", messages.SUCCESS)

@admin.register(Media)
class MediaAdmin(admin.ModelAdmin):
    list_display = ("title", "media_type", "advertiser_link", "display_status", "created_at")
    list_filter = ("status", "media_type", "created_at")
    search_fields = ("title", "advertiser__business_name", "advertiser__first_name")
    readonly_fields = ("file_size_bytes", "created_at", "updated_at")
    actions = ["approve_media_admin", "reject_media_admin"]

    fieldsets = (
        (_("Media Specs"), {"fields": ("advertiser", "title", "media_type", "file", "duration_seconds", "thumbnail")}),
        (_("System Info"), {"fields": ("file_size_bytes", "created_at", "updated_at"), "classes": ("collapse",)}),
        (_("Review Status"), {"fields": ("status", "rejection_reason", "admin_reviewed_by", "manager_reviewed_by")}),
    )

    readonly_fields = ("file_size_bytes", "created_at", "updated_at", "manager_reviewed_by")

    @admin.display(description="Advertiser")
    def advertiser_link(self, obj):
        return obj.advertiser.business_name

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if "status" in form.base_fields:
            # Explicitly define exactly what an Admin is allowed to select
            allowed_admin_choices = [
                (Media.Status.PENDING, "Pending Review"),
                (Media.Status.ADMIN_APPROVED, "Admin Approved"),
                (Media.Status.REJECTED, "Rejected"),
            ]
            form.base_fields["status"].choices = allowed_admin_choices

        if "admin_reviewed_by" in form.base_fields:
            form.base_fields["admin_reviewed_by"].queryset = User.objects.filter(pk=request.user.pk)
            form.base_fields["admin_reviewed_by"].empty_label = None

        return form
    
    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        initial["admin_reviewed_by"] = request.user.pk
        return initial

    def save_model(self, request, obj, form, change):
        if not obj.admin_reviewed_by:
            obj.admin_reviewed_by = request.user
        super().save_model(request, obj, form, change)

    def display_status(self, obj): 
        colors = {
            Media.Status.PENDING: "#e67e22",        # Orange
            #Media.Status.ADMIN_APPROVED: "#3498db", # Blue
            #Media.Status.FULLY_APPROVED: "#2ecc71", # Green
            Media.Status.REJECTED: "#e74c3c",       # Red
        }

        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold;">{}</span>',
            colors.get(obj.status, "#7f8c8d"),
            obj.get_status_display()
        )
    display_status.short_description = "Status"

@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "advertiser_link", "start_date", "end_date", "estimated_price", "display_status")
    list_filter = ("status", "start_date", "end_date")
    search_fields = ("name", "advertiser__business_name")
    inlines = [CampaignSlotInline]
   #  readonly_fields = ("estimated_price", "created_at", "updated_at")

    @admin.display(description="Advertiser")
    def advertiser_link(self, obj):
        return obj.advertiser.business_name
    
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if "admin_reviewed_by" in form.base_fields:
            form.base_fields["admin_reviewed_by"].queryset = User.objects.filter(pk=request.user.pk)
            form.base_fields["admin_reviewed_by"].empty_label = None

        if "status" in form.base_fields:
            # Explicitly define exactly what a Global Admin is allowed to select manually
            allowed_admin_choices = [
                (Campaign.Status.DRAFT, "Draft"),
                (Campaign.Status.PENDING_ADMIN_REVIEW, "Pending Admin Review"),
                (Campaign.Status.PENDING_MANAGER_REVIEW, "Forward to Manager (Admin Approved)"),
                (Campaign.Status.REJECTED, "Rejected"),
            ]
            form.base_fields["status"].choices = allowed_admin_choices
        return form
    
    # Automatically stamps the logged-in admin user if they forward or reject the campaign.
    def save_model(self, request, obj, form, change):
        # Check if the status was changed to manager review or rejected by this admin
        if "status" in form.changed_data and obj.status in [Campaign.Status.PENDING_MANAGER_REVIEW, Campaign.Status.REJECTED]:
            obj.admin_reviewed_by = request.user
            obj.admin_reviewed_at = timezone.now()
        super().save_model(request, obj, form, change)

    def display_status(self, obj):
        colors = {
            Campaign.Status.DRAFT: "#7f8c8d",
            Campaign.Status.PENDING_ADMIN_REVIEW: "#e67e22", 
            Campaign.Status.PENDING_MANAGER_REVIEW: "#3498db", 
            Campaign.Status.APPROVED: "#2ecc71",
            Campaign.Status.REJECTED: "#e74c3c",
            Campaign.Status.ACTIVE: "#1abc9c",
            Campaign.Status.PAUSED: "#f1c40f",
            Campaign.Status.COMPLETED: "#9b59b6",
            Campaign.Status.CANCELLED: "#95a5a6",
        }
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold;">{}</span>',
            colors.get(obj.status, "#7f8c8d"),
            obj.get_status_display()
        )
    display_status.short_description = "Status"

 