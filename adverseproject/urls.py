from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static
from django.conf import settings
from django.views.generic import RedirectView
from rest_framework_simplejwt.views import (TokenObtainPairView, TokenRefreshView,)

urlpatterns = [
    path('', RedirectView.as_view(url='/adverse-auth/login/', permanent=False)),
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('adverse-auth/', include('security.urls')),
    path('adverse/', include('adverse.urls')),
    path('admanager/', include('admanager.urls')),
    path('advertiser/', include('advertiser.urls')),
    path('admin-panel/', include('admin_panel.urls')),
    path('devices/', include('device.urls')),

    # api routes 
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('adverse-api/', include('adverseproject.api_urls'))
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)