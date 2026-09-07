import json

from django.test import TestCase
from django.urls import reverse

from .models import SensorData


class SensorApiTests(TestCase):
    def test_get_sensor_returns_latest_entry(self):
        SensorData.objects.create(water_level=42.5)

        response = self.client.get(reverse("sensor_data"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["latest"]["water_level"], 42.5)
        self.assertIn("timestamp", payload["latest"])

    def test_post_sensor_requires_valid_api_key_and_stores_data(self):
        response = self.client.post(
            reverse("sensor_data"),
            data=json.dumps({"water_level": 45.3}),
            content_type="application/json",
            HTTP_X_API_KEY="WATER_LEVEL_2026",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["message"], "Data stored successfully")
        self.assertTrue(SensorData.objects.filter(water_level=45.3).exists())
