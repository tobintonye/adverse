
from django.urls import path
from . import views

app_name = "admanager"

urlpatterns = [
    path("profile/", views.adManagerProfile, name="profile"),
    path("dashboard/", views.adManagerDashboard, name="dashboard"),
    path("campaigns/", views.campaign_requests, name="campaign_requests"),
    path("campaigns/<uuid:pk>/", views.campaign_request_detail, name="campaign_request_detail"),
    path("settings/", views.adManager_setting, name="settings")
]

