from django.urls import path
from . import views

urlpatterns = [
    path('administrator/disputes/<int:pk>/', views.dispute_review_view, name='admin_dispute_detail'),
    path("administrator/", views.dashboard_view, name="administrator"),
    path("administrator/<slug:section>/", views.dashboard_view, name="administrator_section"),
    path("staff/invite/", views.staff_invitation_view, name="invite_staff"),
    path("reports/orders.csv", views.order_export_view, name="export_orders"),
]