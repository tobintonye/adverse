from django.urls import path
from . import views

app_name = "admanager"

urlpatterns = [
    path("profile/", views.adManagerProfile, name="profile"),
    path("dashboard/", views.adManagerDashboard, name="dashboard"),
    path("settings/", views.adManager_setting, name="settings"),
    path("settings-profile", views.adManagerProfile_settings, name="editProfile")
]