from django.urls import path
 
from .views import ( AdvertiserProfileView, BillboardBrowseView, BillboardBrowseDetailView,
                     MediaListUploadView, MediaDetailView, CampaignListCreateView, CampaignDetailView, CampaignSubmitView, 
                     CampaignCancelView, CampaignPriceEstimateView,
                    )                    
 
urlpatterns = [
    path("profile/", AdvertiserProfileView.as_view(), name="advertiser-profile"),
    path("billboards/", BillboardBrowseView.as_view(), name="advertiser-billboard-list"),
    path("billboards/<uuid:pk>/", BillboardBrowseDetailView.as_view(), name="advertiser-billboard-detail"),
    path("media/", MediaListUploadView.as_view(), name="advertiser-media-list"),
    path("media/<uuid:pk>/", MediaDetailView.as_view(), name="advertiser-media-detail"),

    path("campaigns/", CampaignListCreateView.as_view(), name="advertiser-campaign-list"),
    path("campaigns/estimate/", CampaignPriceEstimateView.as_view(), name="advertiser-campaign-estimate"),
    path("campaigns/<uuid:pk>/", CampaignDetailView.as_view(), name="advertiser-campaign-detail"),
    path("campaigns/<uuid:pk>/submit/", CampaignSubmitView.as_view(), name="advertiser-campaign-submit"),
    path("campaigns/<uuid:pk>/cancel/", CampaignCancelView.as_view(), name="advertiser-campaign-cancel"),
  
]