from django.urls import path, include

urlpatterns = [
    path('auth/', include('security.api.urls')), 
    path('admanager/', include('admanager.api.urls')),
    path('billboards/', include('device.api.urls')),
    path('players/', include('device.api.players_urls')),
    path('advertiser/', include('advertiser.api.urls')),
    path('billboards/', include('scheduling.api.urls')),
]

