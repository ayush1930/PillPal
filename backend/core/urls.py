from django.urls import include, path
from core.web import views
from core.web import password_views
from core.features.inventory import views as inventory_views
from core.features.disputes import views as dispute_views

urlpatterns = []
urlpatterns += [
    path('driver/availability/', views.driver_availability_view, name='driver_availability'),
    path('disputes/', dispute_views.list_view, name='disputes'),
    path('disputes/new/', dispute_views.create_view, name='dispute_create'),
    path('disputes/<int:pk>/', dispute_views.detail_view, name='dispute_detail'),
    path('disputes/<int:pk>/evidence/', dispute_views.evidence_view, name='dispute_evidence'),
    path('inventory/add/', inventory_views.inventory_intake_view, name='inventory_intake'),
    path('media/<path:path>', views.media_file_view, name='media_file'),
    path('', views.home_view, name='home'),
    path('contact/', views.contact_view, name='contact'),
    path('prescriptions/<int:pk>/file/', views.prescription_file_view, name='prescription_file'),
    path('notifications/read-all/', views.notifications_read_all_view, name='notifications_read_all'),
    path('prescriptions/<int:pk>/review/', views.prescription_review_view, name='review_prescription'),
    path('auth', views.authentication_view, name='auth'),
    path('sign-out/', views.logout_view, name='sign_out'),
    path('app/', views.dashboard_view, name='dashboard'),
    path('app/<slug:section>/', views.dashboard_view, name='dashboard_section'),
    path('manage/<slug:resource>/new/', views.resource_form_view, name='resource_create'),
    path('manage/<slug:resource>/<int:pk>/edit/', views.resource_form_view, name='resource_edit'),
    path('manage/<slug:resource>/<int:pk>/<slug:operation>/', views.resource_action_view, name='resource_action'),
    path('orders/<int:pk>/', views.order_detail_view, name='order_detail'),
    path('pharmacies/<int:pk>/medications/', views.medication_catalogue_view, name='catalogue'),
    path('cart/', views.cart_view, name='cart'),
    path('cart/<int:pk>/', views.cart_update_view, name='cart_update'),
    path('password-reset/', password_views.password_reset_view, name='password_reset'),
    path('password-reset/sent/', password_views.password_reset_done_view, name='password_reset_done'),
    path('password-reset/<uidb64>/<token>/', password_views.password_reset_confirm_view, name='password_reset_confirm'),
    path('password-reset/complete/', password_views.password_reset_complete_view, name='password_reset_complete'),
]
