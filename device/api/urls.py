from django.urls import path
from .views import (
    BillboardListCreateView, BillboardDetailView, BillboardUpdateView,
    BillboardDeleteView
)

# using this for now
urlpatterns = [
    path('', BillboardListCreateView.as_view(), name='billboard-list-create'), # GET list, POST
    path("<uuid:pk>/", BillboardDetailView.as_view(), name="billboard-detail"),   # GET {id}
    path("<uuid:pk>/update/", BillboardUpdateView.as_view(), name="billboard-update"),   # PATCH
    path("<uuid:pk>/delete/", BillboardDeleteView.as_view(), name="billboard-delete"),
]
