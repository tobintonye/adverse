from django.urls import path
from . import views

app_name = "admanager"

urlpatterns = [
    path("profile/", views.adManagerProfile, name="profile"),
    path("dashboard/", views.adManagerDashboard, name="dashboard"),
    path("settings/", views.adManager_setting, name="settings"),
    path("settings-profile", views.adManagerProfile_settings, name="editProfile"),
    path("billboards/", views.billboard_list, name="billboard_list"),
    path("billboards/add/", views.billboard_create, name="billboard_create"),
    path("billboards/<uuid:pk>/edit/", views.billboard_edit, name="billboard_edit"),
    path("campaign-requests/", views.campaign_requests, name="campaign_requests"),
    path("campaign-requests/<uuid:pk>/", views.campaign_request_detail, name="campaign_request_detail"),
    path("request-verification/", views.request_verification, name="request_verification"),
    path("withdrawals/", views.withdrawal_list_and_create, name="withdrawal_list"),
    # Bank account management
    path("bank-accounts/add/", views.bank_account_add, name="bank_account_add"),
    path("bank-accounts/<uuid:pk>/default/", views.bank_account_set_default, name="bank_account_set_default"),
    path("bank-accounts/<uuid:pk>/delete/", views.bank_account_delete, name="bank_account_delete"),
]
