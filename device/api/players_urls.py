from django.urls import path
from .views import ( PlayerDeviceListCreateView, PairDeviceView, PlayerDeviceDetailView, 
    PlayerDeviceDisableView, PlayerDeviceRotateTokenView, PlayerHeartbeatView, 
    PlayerSelfRegisterView,  PlayerPairingStatusView      
)

urlpatterns = [
    # PlayerDevice management (dashboard)
    path("", PlayerDeviceListCreateView.as_view(), name="player-list-create"),
    path("pair/", PairDeviceView.as_view(), name="player-pair"),
    path("<uuid:pk>/", PlayerDeviceDetailView.as_view(), name="player-detail"),
    path("<uuid:pk>/disable/", PlayerDeviceDisableView.as_view(), name="player-disable"),
    path("<uuid:pk>/rotate-token/", PlayerDeviceRotateTokenView.as_view(), name="player-rotate-token"),

    # Device-side calls (PlayerDeviceToken auth)
    path("heartbeat/", PlayerHeartbeatView.as_view(), name="player-heartbeat"),
    path("register/", PlayerSelfRegisterView.as_view(), name="player-self-register"),
    path("pairing-status/", PlayerPairingStatusView.as_view(), name="player-pairing-status"),
]