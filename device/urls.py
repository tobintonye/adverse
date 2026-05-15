from django.urls import path
from . import views

app_name = "device"

urlpatterns = [
    path("", views.DeviceList, name="devicesList"),
    path("register/", views.RegisterDevice, name="registerdevice")
]