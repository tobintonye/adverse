from django.urls import path
from . import views

app_name = "adverse"


urlpatterns = [
    path('', views.home, name='home'),
]