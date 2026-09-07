import json
import base64
import os
from datetime import timedelta

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from .models import (
    Device,
    SensorTelemetry,
    CameraFeed,
    Alert,
    SensorData
)


# ============================================================
# CONFIGURATION
# ============================================================

API_KEY = "WATER_LEVEL_2026"
DEVICE_OFFLINE_TIMEOUT = timedelta(seconds=15)


def current_device_status(device):
    """Treat a device as offline when its real heartbeat is stale."""
    if not device.last_seen or timezone.now() - device.last_seen > DEVICE_OFFLINE_TIMEOUT:
        return "OFFLINE"
    return device.status


# ============================================================
# ROOT API
# ============================================================

def index(request):
    return JsonResponse({
        "system": "Smart Drain Monitoring SCADA API",
        "version": "2.0-PostgreSQL-Ready",
        "database": "PostgreSQL Primary",
        "status": "operational",
        "endpoints": [
            "/api/dashboard/",
            "/api/devices/",
            "/api/device/<id>/",
            "/api/device/<id>/sensors/",
            "/api/device/<id>/camera/",
            "/api/device/<id>/alerts/",
            "/api/alerts/",
            "/api/analytics/",
            "/api/telemetry/",
            "/api/camera-snapshot/",
            "/api/test-telemetry/"
        ]
    })


# ============================================================
# DASHBOARD SUMMARY
# ============================================================

def get_dashboard_summary(request):
    """
    Returns aggregated statistics for dashboard overview.
    Data comes from PostgreSQL.
    """

    total_devices = Device.objects.count()

    device_statuses = [current_device_status(device) for device in Device.objects.all()]
    online_devices = device_statuses.count("ONLINE")
    offline_devices = device_statuses.count("OFFLINE")
    warning_devices = device_statuses.count("WARNING")
    critical_devices = device_statuses.count("CRITICAL")

    critical_alerts = Alert.objects.filter(
        severity="CRITICAL",
        acknowledged=False
    ).count()

    active_cameras = CameraFeed.objects.filter(
        status__in=["ACTIVE", "BLOCKED"]
    ).values("device").distinct().count()

    healthy_devices = sum(status in ["ONLINE", "WARNING"] for status in device_statuses)

    # --------------------------------------------------------
    # Latest telemetry for every device
    # --------------------------------------------------------

    latest_telemetries = []

    for dev in Device.objects.all():

        latest = dev.telemetries.order_by(
            "-timestamp"
        ).first()

        if latest:
            latest_telemetries.append(latest)

    # --------------------------------------------------------
    # Average water / gas
    # --------------------------------------------------------

    if latest_telemetries:

        water_levels = [
            t.water_level_cm
            for t in latest_telemetries
            if t.water_level_cm is not None
        ]

        gas_levels = [
            t.gas_ppm
            for t in latest_telemetries
            if t.gas_ppm is not None
        ]

        avg_water_level = (
            round(
                sum(water_levels) / len(water_levels),
                2
            )
            if water_levels
            else None
        )

        avg_gas_level = (
            round(
                sum(gas_levels) / len(gas_levels),
                2
            )
            if gas_levels
            else None
        )

    else:

        avg_water_level = None
        avg_gas_level = None

    return JsonResponse({
        "status": "success",
        "data": {
            "total_devices": total_devices,
            "online_devices": online_devices,
            "offline_devices": offline_devices,
            "warning_devices": warning_devices,
            "critical_devices": critical_devices,
            "critical_alerts": critical_alerts,
            "active_cameras": active_cameras,
            "healthy_devices": healthy_devices,

            # These are REAL database averages
            "average_water_level": avg_water_level,
            "average_gas_level": avg_gas_level
        }
    })


# ============================================================
# ALL DEVICES
# ============================================================

def get_devices(request):
    """
    Returns all registered devices.
    """

    devices = Device.objects.all().order_by("created_at")

    result = []

    for dev in devices:

        latest = dev.telemetries.order_by(
            "-timestamp"
        ).first()

        result.append({
            "id": dev.id,
            "device_id": dev.device_id,
            "name": dev.name,
            "location": dev.location_name,
            "status": current_device_status(dev),

            "last_seen": (
                dev.last_seen.strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                )
                if dev.last_seen
                else None
            ),

            "water_level": (
                latest.water_level_cm
                if latest
                else None
            ),

            "solid_level": (
                latest.solid_level_cm
                if latest
                else None
            ),

            "gas_level": (
                latest.gas_ppm
                if latest
                else None
            ),

            "temperature": (
                latest.temperature_c
                if latest
                else None
            )
        })

    return JsonResponse({
        "status": "success",
        "data": result
    })


# ============================================================
# DEVICE DETAIL
# ============================================================

def get_device_detail(request, device_id):
    """
    Returns specific device information.
    """

    try:

        dev = Device.objects.get(
            device_id=device_id
        )

    except Device.DoesNotExist:

        try:

            dev = Device.objects.get(
                pk=int(device_id)
            )

        except (Device.DoesNotExist, ValueError):

            return JsonResponse({
                "status": "error",
                "message": "Device not found"
            }, status=404)

    latest = dev.telemetries.order_by(
        "-timestamp"
    ).first()

    return JsonResponse({
        "status": "success",
        "data": {

            "id": dev.id,

            "device_id": dev.device_id,

            "name": dev.name,

            "location": dev.location_name,

            "status": current_device_status(dev),

            "last_seen": (
                dev.last_seen.strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                )
                if dev.last_seen
                else None
            ),

            "water_level": (
                latest.water_level_cm
                if latest
                else None
            ),

            "solid_level": (
                latest.solid_level_cm
                if latest
                else None
            ),

            "gas_level": (
                latest.gas_ppm
                if latest
                else None
            ),

            "temperature": (
                latest.temperature_c
                if latest
                else None
            )
        }
    })


# ============================================================
# DEVICE SENSORS
# ============================================================

def get_device_sensors(request, device_id):
    """
    Returns latest sensor values for one device.
    """

    try:

        dev = Device.objects.get(
            device_id=device_id
        )

    except Device.DoesNotExist:

        try:

            dev = Device.objects.get(
                pk=int(device_id)
            )

        except (Device.DoesNotExist, ValueError):

            return JsonResponse({
                "status": "error",
                "message": "Device not found"
            }, status=404)

    latest = dev.telemetries.order_by(
        "-timestamp"
    ).first()

    if not latest:

        return JsonResponse({
            "status": "success",
            "device_id": dev.device_id,
            "connection_status": current_device_status(dev),
            "last_updated": None,
            "sensors": {
                "water_level": None,
                "solid_level": None,
                "gas_sensor": None,
                "temperature": None
            }
        })

    # --------------------------------------------------------
    # Gas status
    # --------------------------------------------------------

    gas_status = "Safe"

    if latest.gas_ppm is not None:

        if latest.gas_ppm > 450:
            gas_status = "Critical"

        elif latest.gas_ppm > 250:
            gas_status = "Warning"

    # --------------------------------------------------------
    # Water status
    # --------------------------------------------------------

    if latest.water_level_cm is not None:

        if latest.water_level_cm > 80:
            water_status = "High Risk"

        elif latest.water_level_cm > 50:
            water_status = "Moderate"

        else:
            water_status = "Normal"

    else:

        water_status = "Unknown"

    # --------------------------------------------------------
    # Solid status
    # --------------------------------------------------------

    if latest.solid_level_cm is not None:

        if latest.solid_level_cm > 40:
            solid_status = "Blockage Warning"

        else:
            solid_status = "Clear"

    else:

        solid_status = "Unknown"

    return JsonResponse({
        "status": "success",

        "device_id": dev.device_id,

        "connection_status": current_device_status(dev),

        "last_updated": (
            latest.timestamp.strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        ),

        "sensors": {

            "water_level": {
                "value": latest.water_level_cm,
                "unit": "cm",
                "status": water_status,
                "health": (
                    "Good"
                    if dev.status in ["ONLINE", "WARNING"]
                    else "Unstable"
                )
            }
            if latest.water_level_cm is not None
            else None,

            "solid_level": {
                "value": latest.solid_level_cm,
                "unit": "cm",
                "status": solid_status,
                "health": "Good"
            }
            if latest.solid_level_cm is not None
            else None,

            "gas_sensor": {
                "value": latest.gas_ppm,
                "unit": "PPM",
                "status": gas_status,
                "health": "Operational"
            }
            if latest.gas_ppm is not None
            else None,

            "temperature": {
                "value": latest.temperature_c,
                "unit": "°C",
                "status": "Normal",
                "health": "Good"
            }
            if latest.temperature_c is not None
            else None
        }
    })


# ============================================================
# DEVICE CAMERA
# ============================================================

def get_device_camera(request, device_id):
    """
    Returns the latest REAL Raspberry Pi camera result.
    """

    try:

        dev = Device.objects.get(
            device_id=device_id
        )

    except Device.DoesNotExist:

        try:

            dev = Device.objects.get(
                pk=int(device_id)
            )

        except (Device.DoesNotExist, ValueError):

            return JsonResponse({
                "status": "error",
                "message": "Device not found"
            }, status=404)

    # --------------------------------------------------------
    # Get latest camera feed
    # --------------------------------------------------------

    camera_feed = dev.camera_feeds.order_by(
        "-timestamp"
    ).first()

    if not camera_feed:

        return JsonResponse({
            "status": "success",

            "device_id": dev.device_id,

            "camera_status": "OFFLINE",

            "live_feed": None,

            "snapshot": None,

            "ai_detection": "OFFLINE",

            "detected_objects": [],

            "blockage_percentage": None,

            "timestamp": None,

            "message": "Waiting for Raspberry Pi camera..."
        })

    return JsonResponse({
        "status": "success",

        "device_id": dev.device_id,

        "camera_status": camera_feed.status,

        "live_feed": camera_feed.image_url,

        "snapshot": camera_feed.image_url,

        "timestamp": (
            camera_feed.timestamp.strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        ),

        "ai_detection": (
            "ACTIVE"
            if camera_feed.status != "INACTIVE"
            else "OFFLINE"
        ),

        "detected_objects": (
            camera_feed.detected_objects
            if camera_feed.detected_objects
            else []
        ),

        "blockage_percentage": (
            camera_feed.blockage_percentage
        )
    })


# ============================================================
# DEVICE ALERTS
# ============================================================

def get_device_alerts(request, device_id):
    """
    Returns alerts associated with one device.
    """

    try:

        dev = Device.objects.get(
            device_id=device_id
        )

    except Device.DoesNotExist:

        try:

            dev = Device.objects.get(
                pk=int(device_id)
            )

        except (Device.DoesNotExist, ValueError):

            return JsonResponse({
                "status": "error",
                "message": "Device not found"
            }, status=404)

    alerts = dev.alerts.all()[:50]

    result = []

    for a in alerts:

        result.append({
            "id": a.id,

            "time": a.timestamp.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),

            "device": dev.device_id,

            "device_name": dev.name,

            "severity": a.severity,

            "alert_type": a.alert_type,

            "description": a.description,

            "acknowledged": a.acknowledged
        })

    return JsonResponse({
        "status": "success",
        "data": result
    })


# ============================================================
# ALL ALERTS
# ============================================================

def get_all_alerts(request):
    """
    Returns system-wide alerts.
    """

    alerts = Alert.objects.select_related(
        "device"
    ).all()[:100]

    result = []

    for a in alerts:

        result.append({

            "id": a.id,

            "time": a.timestamp.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),

            "device": a.device.device_id,

            "device_name": a.device.name,

            "location": a.device.location_name,

            "severity": a.severity,

            "alert_type": a.alert_type,

            "description": a.description,

            "acknowledged": a.acknowledged
        })

    return JsonResponse({
        "status": "success",
        "data": result
    })


# ============================================================
# ANALYTICS
# ============================================================

def get_analytics(request):
    """
    Returns telemetry history for dashboard charts.
    """

    device_id = request.GET.get(
        "device_id"
    )

    if device_id:

        telemetries = SensorTelemetry.objects.filter(
            device__device_id=device_id
        ).order_by(
            "timestamp"
        )[:50]

    else:

        telemetries = SensorTelemetry.objects.order_by(
            "timestamp"
        )[:50]

    history = []

    for t in telemetries:

        history.append({

            "time": t.timestamp.strftime(
                "%H:%M:%S"
            ),

            "device_id": t.device.device_id,

            "water_level": t.water_level_cm,

            "solid_level": t.solid_level_cm,

            "gas_level": t.gas_ppm,

            "temperature": t.temperature_c
        })

    return JsonResponse({
        "status": "success",
        "data": history
    })


# ============================================================
# REAL SENSOR TELEMETRY
# ============================================================

@csrf_exempt
def post_telemetry(request):
    """
    Receives REAL sensor data from ESP8266 / ESP32.
    """

    if request.method != "POST":

        return JsonResponse({
            "status": "error",
            "message": "Method not allowed"
        }, status=405)

    # --------------------------------------------------------
    # API KEY
    # --------------------------------------------------------

    api_key = request.headers.get(
        "X-API-KEY"
    )

    if api_key and api_key != API_KEY:

        return JsonResponse({
            "status": "error",
            "message": "Invalid API key"
        }, status=401)

    # --------------------------------------------------------
    # JSON
    # --------------------------------------------------------

    try:

        payload = json.loads(
            request.body
        )

    except json.JSONDecodeError:

        return JsonResponse({
            "status": "error",
            "message": "Invalid JSON payload"
        }, status=400)

    # --------------------------------------------------------
    # DEVICE ID
    # --------------------------------------------------------

    device_id = payload.get(
        "device_id",
        "DRAIN-001"
    )

    # --------------------------------------------------------
    # GET / CREATE DEVICE
    # --------------------------------------------------------

    device, created = Device.objects.get_or_create(

        device_id=device_id,

        defaults={
            "name": f"Drain Monitoring Node ({device_id})",
            "location_name": "Smart City Drain Station A1",
            "status": "ONLINE"
        }
    )

    # --------------------------------------------------------
    # UPDATE DEVICE
    # --------------------------------------------------------

    device.status = "ONLINE"

    device.last_seen = timezone.now()

    if "battery_pct" in payload:

        device.battery_percentage = payload[
            "battery_pct"
        ]

    if "signal_dbm" in payload:

        device.signal_strength_dbm = payload[
            "signal_dbm"
        ]

    device.save()

    # --------------------------------------------------------
    # SAVE TELEMETRY
    # --------------------------------------------------------

    telemetry = SensorTelemetry.objects.create(

        device=device,

        timestamp=timezone.now(),

        water_level_cm=payload.get(
            "water_level_cm"
        ),

        solid_level_cm=payload.get(
            "solid_level_cm"
        ),

        gas_ppm=payload.get(
            "gas_ppm"
        ),

        temperature_c=payload.get(
            "temperature_c"
        ),

        humidity_pct=payload.get(
            "humidity_pct"
        ),

        rain_detected=payload.get(
            "rain_detected"
        ),

        battery_pct=payload.get(
            "battery_pct"
        ),

        signal_dbm=payload.get(
            "signal_dbm"
        )
    )

    # --------------------------------------------------------
    # WATER ALERT
    # --------------------------------------------------------

    water = payload.get(
        "water_level_cm"
    )

    if water is not None and water > 75:

        Alert.objects.create(

            device=device,

            severity="CRITICAL",

            alert_type="High Water Level",

            description=(
                "Water level exceeded safety "
                f"threshold: {water} cm"
            )
        )

        device.status = "CRITICAL"

        device.save()

    # --------------------------------------------------------
    # GAS ALERT
    # --------------------------------------------------------

    gas = payload.get(
        "gas_ppm"
    )

    if gas is not None and gas > 400:

        Alert.objects.create(

            device=device,

            severity="CRITICAL",

            alert_type="Gas Leakage",

            description=(
                "Hazardous gas concentration "
                f"detected: {gas} PPM"
            )
        )

        device.status = "WARNING"

        device.save()

    return JsonResponse({

        "status": "success",

        "message": (
            "Real telemetry packet "
            "written to PostgreSQL"
        ),

        "telemetry_id": telemetry.id,

        "device_id": device.device_id
    })


# ============================================================
# REAL RASPBERRY PI CAMERA
# ============================================================

@csrf_exempt
def post_camera_snapshot(request):
    """
    Receives REAL camera images from Raspberry Pi.

    Expected multipart/form-data:

        image = JPEG image

        device_id = DRAIN-001

        detected_objects = ["Debris", "Plastic Bottle"]

        blockage_percentage = 42.5
    """

    if request.method != "POST":

        return JsonResponse({
            "status": "error",
            "message": "Method not allowed"
        }, status=405)

    # --------------------------------------------------------
    # API KEY
    # --------------------------------------------------------

    api_key = request.headers.get(
        "X-API-KEY"
    )

    if api_key and api_key != API_KEY:

        return JsonResponse({
            "status": "error",
            "message": "Invalid API key"
        }, status=401)

    # --------------------------------------------------------
    # DEVICE ID
    # --------------------------------------------------------

    device_id = (
        request.POST.get("device_id")
        or request.headers.get("X-DEVICE-ID")
        or "DRAIN-001"
    )

    # --------------------------------------------------------
    # GET IMAGE
    # --------------------------------------------------------

    uploaded_file = (
        request.FILES.get("image")
        or request.FILES.get("file")
    )

    # --------------------------------------------------------
    # NO IMAGE = ERROR
    # --------------------------------------------------------

    if not uploaded_file:

        return JsonResponse({

            "status": "error",

            "message": (
                "No real Raspberry Pi "
                "camera image received"
            )
        }, status=400)

    # --------------------------------------------------------
    # DETECTED OBJECTS
    # --------------------------------------------------------

    detected_objects_raw = request.POST.get(
        "detected_objects",
        "[]"
    )

    try:

        detected_objs = json.loads(
            detected_objects_raw
        )

        if not isinstance(
            detected_objs,
            list
        ):

            detected_objs = []

    except Exception:

        detected_objs = []

    # --------------------------------------------------------
    # BLOCKAGE %
    # --------------------------------------------------------

    blockage_raw = request.POST.get(
        "blockage_percentage",
        "0"
    )

    try:

        blockage_pct = float(
            blockage_raw
        )

    except (ValueError, TypeError):

        blockage_pct = 0.0

    # Keep percentage inside valid range

    blockage_pct = max(
        0.0,
        min(
            100.0,
            blockage_pct
        )
    )

    # --------------------------------------------------------
    # GET / CREATE DEVICE
    # --------------------------------------------------------

    device, created = Device.objects.get_or_create(

        device_id=device_id,

        defaults={

            "name": (
                f"Raspberry Pi Camera "
                f"({device_id})"
            ),

            "location_name": (
                "Smart City Drain Channel"
            ),

            "status": "ONLINE"
        }
    )

    # --------------------------------------------------------
    # UPDATE DEVICE HEARTBEAT
    # --------------------------------------------------------

    device.last_seen = timezone.now()

    device.status = "ONLINE"

    device.save()

    # --------------------------------------------------------
    # SAVE REAL IMAGE
    # --------------------------------------------------------

    timestamp = int(
        timezone.now().timestamp()
    )

    filename = (
        f"cam_{device_id}_{timestamp}.jpg"
    )

    rel_path = (
        f"camera_snapshots/{filename}"
    )

    path = default_storage.save(

        rel_path,

        ContentFile(
            uploaded_file.read()
        )
    )

    # --------------------------------------------------------
    # IMAGE URL
    # --------------------------------------------------------

    image_url = (
        settings.MEDIA_URL.rstrip("/")
        + "/"
        + path
    )

    # --------------------------------------------------------
    # CAMERA STATUS
    # --------------------------------------------------------

    if blockage_pct > 50:

        camera_status = "BLOCKED"

    else:

        camera_status = "ACTIVE"

    # --------------------------------------------------------
    # SAVE CAMERA FEED
    # --------------------------------------------------------

    cam_feed = CameraFeed.objects.create(

        device=device,

        timestamp=timezone.now(),

        image_url=image_url,

        status=camera_status,

        detected_objects=detected_objs,

        blockage_percentage=blockage_pct
    )

    # --------------------------------------------------------
    # CAMERA BLOCKAGE ALERT
    # --------------------------------------------------------

    if blockage_pct > 50:

        Alert.objects.create(

            device=device,

            severity="CRITICAL",

            alert_type="Camera Blockage",

            description=(
                "Raspberry Pi YOLO detected "
                f"{blockage_pct}% channel obstruction"
            )
        )

        device.status = "CRITICAL"

        device.save()

    # --------------------------------------------------------
    # RESPONSE
    # --------------------------------------------------------

    return JsonResponse({

        "status": "success",

        "message": (
            "REAL Raspberry Pi camera "
            "image stored in PostgreSQL"
        ),

        "feed_id": cam_feed.id,

        "device_id": device.device_id,

        "image_url": image_url,

        "detected_objects": detected_objs,

        "blockage_percentage": blockage_pct,

        "camera_status": camera_status
    })


# ============================================================
# REGISTER DEVICE
# ============================================================

@csrf_exempt
def register_device(request):
    """
    Register Raspberry Pi / ESP8266 device.
    """

    if request.method != "POST":

        return JsonResponse({
            "status": "error",
            "message": "Method not allowed"
        }, status=405)

    try:

        payload = json.loads(
            request.body
        )

        device_id = payload.get(
            "device_id"
        )

        name = payload.get(
            "name"
        )

        location = payload.get(
            "location",
            "Municipal Drain Sector"
        )

        lat = payload.get(
            "latitude"
        )

        lng = payload.get(
            "longitude"
        )

        # ----------------------------------------------------
        # VALIDATION
        # ----------------------------------------------------

        if not device_id or not name:

            return JsonResponse({

                "status": "error",

                "message": (
                    "device_id and name "
                    "are required"
                )
            }, status=400)

        # ----------------------------------------------------
        # CREATE DEVICE
        # ----------------------------------------------------

        device, created = Device.objects.get_or_create(

            device_id=device_id,

            defaults={

                "name": name,

                "location_name": location,

                "latitude": lat,

                "longitude": lng,

                "status": "OFFLINE"
            }
        )

        return JsonResponse({

            "status": "success",

            "created": created,

            "device": {

                "id": device.id,

                "device_id": device.device_id,

                "name": device.name,

                "location": device.location_name,

                "status": device.status
            }
        })

    except Exception as exc:

        return JsonResponse({

            "status": "error",

            "message": str(exc)

        }, status=500)


# ============================================================
# TEST TELEMETRY
# ============================================================

@csrf_exempt
def post_test_telemetry(request):
    """
    TEST ONLY.

    This endpoint generates fake/random sensor data.
    Do NOT use this endpoint for the real Raspberry Pi/
    ESP8266 system.
    """

    if request.method != "POST":

        return JsonResponse({

            "status": "error",

            "message": "Method not allowed"

        }, status=405)

    import random

    device_id = request.GET.get(
        "device_id",
        "DRAIN-001"
    )

    device, _ = Device.objects.get_or_create(

        device_id=device_id,

        defaults={

            "name": "Test Drain Node",

            "location_name": (
                "Test Location"
            ),

            "status": "ONLINE"
        }
    )

    device.status = "ONLINE"

    device.last_seen = timezone.now()

    device.save()

    # --------------------------------------------------------
    # FAKE DATA - TEST ONLY
    # --------------------------------------------------------

    water = round(
        random.uniform(20.0, 85.0),
        1
    )

    solid = round(
        random.uniform(5.0, 45.0),
        1
    )

    gas = round(
        random.uniform(110.0, 480.0),
        1
    )

    temp = round(
        random.uniform(24.0, 36.0),
        1
    )

    humidity = round(
        random.uniform(40.0, 80.0),
        1
    )

    rain = random.choice(
        [True, False]
    )

    batt = round(
        random.uniform(60.0, 100.0),
        1
    )

    sig = random.randint(
        -80,
        -40
    )

    telemetry = SensorTelemetry.objects.create(

        device=device,

        timestamp=timezone.now(),

        water_level_cm=water,

        solid_level_cm=solid,

        gas_ppm=gas,

        temperature_c=temp,

        humidity_pct=humidity,

        rain_detected=rain,

        battery_pct=batt,

        signal_dbm=sig
    )

    return JsonResponse({

        "status": "success",

        "message": (
            "TEST telemetry created"
        ),

        "data": {

            "device_id": device.device_id,

            "water_level_cm": water,

            "solid_level_cm": solid,

            "gas_ppm": gas,

            "temperature_c": temp
        }
    })