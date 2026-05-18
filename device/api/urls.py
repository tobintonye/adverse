from django.urls import path
from .views import (
    BillboardListCreateView, BillboardDetailView, BillboardUpdateView,
    BillboardDeleteView, PlayerDeviceListCreateView, PairDeviceView, PlayerDeviceDetailView, PlayerDeviceDisableView
    )

# using this for now
urlpatterns = [
    path('', BillboardListCreateView.as_view(), name='billboard-list-create'), # GET list, POST
    path("<uuid:pk>/", BillboardDetailView.as_view(), name="billboard-detail"),   # GET {id}
    path("<uuid:pk>/update/", BillboardUpdateView.as_view(), name="billboard-update"),   # PATCH
    path("<uuid:pk>/delete/", BillboardDeleteView.as_view(), name="billboard-delete"),
  
    # PlayerDevice management (dashboard)
    path("players/", PlayerDeviceListCreateView.as_view(), name="player-list-create"),
    path("players/pair/", PairDeviceView.as_view(), name="player-pair"),
    path("players/<uuid:pk>/", PlayerDeviceDetailView.as_view(), name="player-detail"),
    path("players/<uuid:pk>/disable/", PlayerDeviceDisableView.as_view(), name="player-disable"),
    
    #path("<uuid:pk>/rotate-token/", DeviceRotateTokenView.as_view(), name="device-rotate-token"),

    #path('heartbeat/', DeviceHeartbeatView.as_view(), name='heartbeat'), 
]
