"""Only called after the user enables the city disclosure in Settings."""

import json
import time
from urllib.request import urlopen
from urllib.parse import urlencode


class Weather:
    def __init__(self):
        self.city = ""
        self.expires = 0
        self.text = ""

    @staticmethod
    def request(endpoint, values):
        with urlopen(endpoint + "?" + urlencode(values), timeout=2) as response:
            return json.loads(response.read(65536))

    def current(self, city):
        city = (city or "").strip()[:80]
        if not city:
            return ""
        if city == self.city and time.monotonic() < self.expires:
            return self.text
        self.city, self.text = city, ""
        self.expires = time.monotonic() + 3600
        try:
            data = self.request(
                "https://geocoding-api.open-meteo.com/v1/search",
                {"name": city, "count": 1, "language": "zh"},
            )
            place = data["results"][0]
            data = self.request(
                "https://api.open-meteo.com/v1/forecast",
                {
                    "latitude": place["latitude"],
                    "longitude": place["longitude"],
                    "current": "temperature_2m,precipitation,apparent_temperature,relative_humidity_2m,wind_speed_10m",
                },
            )
            now = data["current"]
            self.text = f"{place['name']} · {now['temperature_2m']} °C · 降水 {now['precipitation']} mm"
            for key, label, unit in [
                ("apparent_temperature", "体感", "°C"),
                ("relative_humidity_2m", "湿度", "%"),
                ("wind_speed_10m", "风速", "km/h"),
            ]:
                if key in now:
                    self.text += f" · {label} {now[key]} {unit}"
            self.text += " · Open-Meteo"
        except (OSError, ValueError, KeyError, IndexError, TypeError):
            pass
        return self.text
