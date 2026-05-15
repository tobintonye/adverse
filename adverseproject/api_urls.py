from django.urls import path, include

urlpatterns = [
    path('auth/', include('security.api.urls')), 
    path('devices/', include('device.api.urls')),
]

