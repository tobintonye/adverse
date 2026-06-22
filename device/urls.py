from django.urls import path
from . import views

app_name = "device"

urlpatterns = [
    path("billboards/", views.billboard_list, name="billboard_list"),
    path("billboards/add/", views.billboard_create, name="billboard_create"),
    path("billboards/<uuid:pk>/edit/", views.billboard_edit, name="billboard_edit"),
    path("billboards/<uuid:pk>/schedule/", views.billboard_schedule, name="billboard_schedule"),
    path("billboards/<uuid:pk>/device/", views.device_detail, name="device_detail"),
    path("pair/", views.device_pair, name="device_pair"),
]