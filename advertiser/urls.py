from django.urls import path
from . import views

app_name = "advertiser"

urlpatterns = [
    path("create-profile/", views.advertiser_create_profile, name="create_profile"),
    path("edit-profile/", views.advertiser_edit_profile, name="edit_profile"),
    path("dashboard/", views.advertiserDashboard, name="dashboard"),
    path("request-verification/", views.advertiser_request_verification, name="request_verification"),
    # Media
    path("media/", views.media_library, name="media_library"),
    path("media/upload/", views.upload_media, name="upload_media"),
    path("media/<uuid:pk>/delete/", views.media_delete, name="media_delete"),
    path("media/<uuid:pk>/preview/", views.media_preview, name="media_preview"),
    path("media/picker/", views.media_picker, name="media_picker"),

    # Billboards (browse only — advertisers don't own billboards)
    path("billboards/", views.browse_billboards, name="browse_billboards"),
    # Campaigns
    path("campaigns/", views.campaign_list, name="campaign_list"),
    path("campaigns/create/", views.campaign_create, name="campaign_create"),
    path("campaigns/<uuid:pk>/", views.campaign_detail, name="campaign_detail"),
    path("campaigns/<uuid:pk>/run-again/", views.campaign_run_again, name="campaign_run_again"),
    path("campaigns/<uuid:pk>/status/", views.campaign_status_fragment, name="campaign_status_fragment"),
    path("campaigns/<uuid:pk>/edit/", views.campaign_edit, name="campaign_edit"),
    path("campaigns/<uuid:pk>/pay/", views.campaign_pay, name="campaign_pay"), 
    path("campaigns/<uuid:pk>/playback-log/", views.campaign_playback_log, name="campaign_playback_log"),
    # advertiser/urls.py — add
    path("campaigns/<uuid:pk>/select-dates/", views.campaign_select_dates, name="campaign_select_dates"),
    path("settings/", views.advertiser_settings, name="settings"),
]