from django.urls import path
from .views import ( AdManagerCreateView, MyAdManagerProfileView, AdManagerCampaignRequestsListView, 
                    AdManagerApproveCampaignView, AdManagerRejectCampaignView    
)

urlpatterns = [
    path("profile/create/", AdManagerCreateView.as_view(), name="admanager-create"),
    path("profile/me/", MyAdManagerProfileView.as_view(), name="admanager-detail-update"),
    path("campaign-requests/", AdManagerCampaignRequestsListView.as_view(), name="admanager-campaign-requests"),

    path("campaign-requests/<uuid:pk>/approve/", AdManagerApproveCampaignView.as_view(), name="admanager-campaign-approve"),
    path("campaign-requests/<uuid:pk>/reject/", AdManagerRejectCampaignView.as_view(), name="admanager-campaign-reject"),
]   