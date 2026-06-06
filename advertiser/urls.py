from django.urls import path
from . import views

app_name = "advertiser"

urlpatterns = [
    path("profile/", views.create_advertiser_profile, name="create_profile"),
    path("dashboard/", views.advertiser_dashboard, name="dashboard"),
    path("billboards/", views.browse_billboards, name="browse_billboards"),
    path("media/", views.media_library, name="media_library"),
    path("media/upload/", views.upload_media, name="upload_media"),
    path("campaigns/", views.campaign_list, name="campaign_list"),
    path("campaigns/create/", views.campaign_create, name="campaign_create"),
    path("campaigns/<uuid:pk>/", views.campaign_detail, name="campaign_detail"),
    path("campaigns/<uuid:pk>/edit/", views.campaign_edit, name="campaign_edit"),
    path("settings/", views.advertiser_settings, name="settings"),
    path("request-verification/", views.request_verification, name="request_verification"),
]
