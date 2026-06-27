
from django.urls import path
from . import views

app_name = "admanager"

urlpatterns = [
    path("profile/", views.adManagerProfile, name="profile"),
    path("dashboard/", views.adManagerDashboard, name="dashboard"),
    path("campaigns/", views.campaign_requests, name="campaign_requests"),
    path("campaigns/<uuid:pk>/", views.campaign_request_detail, name="campaign_request_detail"),
    path("settings/", views.adManager_setting, name="settings"),
    path("payment/setup/", views.payment_setup, name="payment_setup"),
    path("payment/update-bank/", views.payment_update_bank, name="payment_update_bank"),
    path("payment/verify/", views.payment_verify_subaccount, name="payment_verify_subaccount"),
]

