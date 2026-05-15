from django.urls import path
from .views import (
    DeviceRegisterView, DeviceHeartbeatView, DeviceUpdateView,
    DeviceDetailView, DeviceRotateTokenView)

# using this for now
urlpatterns = [
    path('', DeviceRegisterView.as_view(), name='register'), # GET list, POST
    path("<uuid:pk>/", DeviceDetailView.as_view(), name="device-detail"),   # GET {id}
    path("<uuid:pk>/update/", DeviceUpdateView.as_view(), name="device-update"),   # PATCH
    path("<uuid:pk>/rotate-token/", DeviceRotateTokenView.as_view(), name="device-rotate-token"),

    path('heartbeat/', DeviceHeartbeatView.as_view(), name='heartbeat'), 
]
