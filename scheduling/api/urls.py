from django.urls import path

from .views import (BillboardScheduleView, BillboardCapacityView, BillboardCapacityRecalculateView,
                    CapacityCheckView, CampaignScheduleGenerateView, CampaignSchedulePreviewView, ScheduleGenerationLogListView, 
                    BillboardHourlyLoadView
                    )

urlpatterns = [
    path("billboards/<uuid:pk>/schedule/", BillboardScheduleView.as_view(), name="billboard-schedule"),
    path("billboards/<uuid:pk>/capacity/", BillboardCapacityView.as_view(),  name="billboard-capacity"),
    path("billboards/<uuid:pk>/capacity/recalculate/", BillboardCapacityRecalculateView.as_view(), name="billboard-capacity-recalculate"),
    path("billboards/<uuid:pk>/hourly-load/", BillboardHourlyLoadView.as_view(), name="billboard-hourly-load"),

    # Capacity check before booking
    path("capacity-check/", CapacityCheckView.as_view(), name="capacity-check"),
 
    # Campaign schedule
    path("campaigns/<uuid:pk>/generate/", CampaignScheduleGenerateView.as_view(), name="campaign-schedule-generate"),
    path("campaigns/<uuid:pk>/preview/", CampaignSchedulePreviewView.as_view(), name="campaign-schedule-preview"),
 
    # Admin logs
    path("logs/", ScheduleGenerationLogListView.as_view(), name="schedule-logs"),

]
