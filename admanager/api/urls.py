from django.urls import path
from .views import (
    AdManagerCreateView,
    MyAdManagerProfileView
)

urlpatterns = [
    path("profile/create/", AdManagerCreateView.as_view(), name="admanager-create"),
    path("profile/me/", MyAdManagerProfileView.as_view(), name="admanager-detail-update"),
]