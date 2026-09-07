from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("api/dashboard/", views.get_dashboard_summary, name="dashboard_summary"),
    path("api/devices/", views.get_devices, name="get_devices"),
    path("api/device/register/", views.register_device, name="register_device"),
    path("api/device/<str:device_id>/", views.get_device_detail, name="get_device_detail"),
    path("api/device/<str:device_id>/sensors/", views.get_device_sensors, name="get_device_sensors"),
    path("api/device/<str:device_id>/camera/", views.get_device_camera, name="get_device_camera"),
    path("api/device/<str:device_id>/alerts/", views.get_device_alerts, name="get_device_alerts"),
    path("api/alerts/", views.get_all_alerts, name="get_all_alerts"),
    path("api/analytics/", views.get_analytics, name="get_analytics"),
    path("api/telemetry/", views.post_telemetry, name="post_telemetry"),
    path("api/camera-snapshot/", views.post_camera_snapshot, name="post_camera_snapshot"),
    path("api/test-telemetry/", views.post_test_telemetry, name="post_test_telemetry"),
]