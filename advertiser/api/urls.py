from django.urls import path
 
from .views import ( AdvertiserProfileView,
    BillboardBrowseView, BillboardBrowseDetailView,
)
 
urlpatterns = [
    path("profile/", AdvertiserProfileView.as_view(), name="advertiser-profile"),
    path("billboards/", BillboardBrowseView.as_view(), name="advertiser-billboard-list"),
    path("billboards/<uuid:pk>/", BillboardBrowseDetailView.as_view(), name="advertiser-billboard-detail"),
]