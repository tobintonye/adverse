from django.urls import path

from .views import (BillboardScheduleView, BillboardCapacityView, BillboardCapacityRecalculateView,
                    CapacityCheckView, CampaignScheduleGenerateView, CampaignSchedulePreviewView, ScheduleGenerationLogListView, 
                    BillboardHourlyLoadView, BillboardHourDailyBreakdownView
                    )

urlpatterns = [
    path("<uuid:pk>/schedule/", BillboardScheduleView.as_view(), name="billboard-schedule"),
    path("<uuid:pk>/capacity/", BillboardCapacityView.as_view(),  name="billboard-capacity"),
    path("<uuid:pk>/capacity/recalculate/", BillboardCapacityRecalculateView.as_view(), name="billboard-capacity-recalculate"),
     path("<uuid:pk>/hourly-load/", BillboardHourlyLoadView.as_view(), name="billboard-hourly-load"),
    path("<uuid:pk>/hourly-load/<int:hour>/daily/", BillboardHourDailyBreakdownView.as_view(), name="billboard-hourly-load-daily"),
    
    # Capacity check before booking
    path("capacity-check/", CapacityCheckView.as_view(), name="capacity-check"),
 
    # Campaign schedule
    path("campaigns/<uuid:pk>/generate/", CampaignScheduleGenerateView.as_view(), name="campaign-schedule-generate"),
    path("campaigns/<uuid:pk>/preview/", CampaignSchedulePreviewView.as_view(), name="campaign-schedule-preview"),
 
    # Admin logs
    path("logs/", ScheduleGenerationLogListView.as_view(), name="schedule-logs"),

]
