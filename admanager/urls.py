
from django.urls import path
from . import views

app_name = "admanager"

urlpatterns = [
    path("profile/", views.adManagerProfile, name="profile"),
    path("dashboard/", views.adManagerDashboard, name="dashboard"),
    path("campaigns/", views.campaign_requests, name="campaign_requests"),
    path("campaigns/<uuid:pk>/", views.campaign_request_detail, name="campaign_request_detail"),
    path("campaigns/<uuid:pk>/schedule-log/", views.campaign_schedule_log, name="campaign_schedule_log"),  
    path("campaigns/<uuid:pk>/playback-log/", views.campaign_playback_log, name="campaign_playback_log"),
    path("settings/", views.adManager_setting, name="settings"),
    path("payment/setup/", views.payment_setup, name="payment_setup"),
    path("payment/update-bank/", views.payment_update_bank, name="payment_update_bank"),
    path("payment/verify/", views.payment_verify_subaccount, name="payment_verify_subaccount"),
    path("withdraw/", views.request_withdrawal, name="request_withdrawal"),

]

