from django.urls import path
from . import views

app_name = "admin_panel"

urlpatterns = [
    path("", views.admin_dashboard, name="dashboard"),
    path("advertisers/", views.advertiser_list, name="advertiser_list"),
    path("media/", views.media_review_list, name="media_review"),
    path("campaigns/", views.campaign_review_list, name="campaign_review"),
    path("campaigns/<uuid:pk>/", views.admin_campaign_detail, name="campaign_detail"),
    path("ad-managers/", views.ad_manager_list, name="ad_manager_list"),
    path("revenue-settings/", views.revenue_settings, name="revenue_settings"),
    path("withdrawals/", views.admin_withdrawal_list, name="withdrawal_list"),
]
