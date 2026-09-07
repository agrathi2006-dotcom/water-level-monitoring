from django.db import models
from django.utils import timezone


class Device(models.Model):
    STATUS_CHOICES = [
        ('ONLINE', 'Online'),
        ('OFFLINE', 'Offline'),
        ('WARNING', 'Warning'),
        ('CRITICAL', 'Critical'),
    ]

    device_id = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    location_name = models.CharField(max_length=256, default="Municipal Drain Zone 1")
    latitude = models.FloatField(default=17.385043)
    longitude = models.FloatField(default=78.486671)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='OFFLINE')
    firmware_version = models.CharField(max_length=32, default="v1.0.4-esp32")
    battery_percentage = models.FloatField(null=True, blank=True)
    signal_strength_dbm = models.IntegerField(null=True, blank=True)
    last_seen = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.device_id})"


class SensorTelemetry(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="telemetries")
    timestamp = models.DateTimeField(default=timezone.now)
    water_level_cm = models.FloatField(null=True, blank=True)
    solid_level_cm = models.FloatField(null=True, blank=True)
    gas_ppm = models.FloatField(null=True, blank=True)
    temperature_c = models.FloatField(null=True, blank=True)
    humidity_pct = models.FloatField(null=True, blank=True)
    rain_detected = models.BooleanField(default=False, null=True, blank=True)
    battery_pct = models.FloatField(null=True, blank=True)
    signal_dbm = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.device.device_id} @ {self.timestamp}"


class CameraFeed(models.Model):
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('INACTIVE', 'Inactive'),
        ('BLOCKED', 'Blockage Detected'),
    ]

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="camera_feeds")
    timestamp = models.DateTimeField(default=timezone.now)
    image_url = models.CharField(max_length=512, null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='INACTIVE')
    detected_objects = models.JSONField(default=list, blank=True)
    blockage_percentage = models.FloatField(default=0.0)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"Camera {self.device.device_id} @ {self.timestamp}"


class Alert(models.Model):
    SEVERITY_CHOICES = [
        ('INFO', 'Info'),
        ('WARNING', 'Warning'),
        ('CRITICAL', 'Critical'),
    ]

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="alerts")
    timestamp = models.DateTimeField(default=timezone.now)
    severity = models.CharField(max_length=16, choices=SEVERITY_CHOICES, default='INFO')
    alert_type = models.CharField(max_length=64)
    description = models.TextField()
    acknowledged = models.BooleanField(default=False)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"[{self.severity}] {self.device.device_id}: {self.alert_type}"


class SensorData(models.Model):
    """Legacy model maintained for backwards compatibility."""
    water_level = models.FloatField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.water_level} at {self.timestamp}"
