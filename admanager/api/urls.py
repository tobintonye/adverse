from django.urls import path
from .views import (
    AdManagerCreateView, AdManagerProfileView, AdManagerDashboardView, AdManagerBankAccountView,
    AdManagerCampaignRequestsListView, AdManagerCampaignDetailView, AdManagerCampaignReviewView,
)

urlpatterns = [
    path("profile/create/", AdManagerCreateView.as_view(), name="admanager-create"),
    path("profile/me/", AdManagerProfileView.as_view(), name="admanager-detail-update"),
    path('bank-account/', AdManagerBankAccountView.as_view(), name='admanager-bank-account'),
    path('dashboard/', AdManagerDashboardView.as_view(), name='admanager-dashboard'),
    path("campaign/", AdManagerCampaignRequestsListView.as_view(), name="admanager-campaign-requests"),
    path('campaign/<uuid:pk>/', AdManagerCampaignDetailView.as_view(), name='admanager-campaign-detail'),
    path('campaigns/<uuid:pk>/review/', AdManagerCampaignReviewView.as_view(), name='admanager-campaign-review'),
]