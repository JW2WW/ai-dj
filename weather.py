"""Weather fetcher: free current conditions via Open-Meteo (no API key needed).

Uses the Open-Meteo API which is free and requires no registration.
Returns human-readable weather summaries for DJ announcements.
"""
import json
import logging
from datetime import datetime
from pathlib import Path

import requests

from config import get_config

CACHE_FILE = Path(__file__).parent / "data" / "weather_cache.json"
CACHE_TTL_SECONDS = 600  # Re-fetch every 10 minutes

WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

USER_AGENT = "AI-DJ/1.0 (+https://github.com/JW2WW/Radio-DJ-for-MP3s)"


def _cached_weather() -> dict | None:
    try:
        if CACHE_FILE.exists():
            data = json.loads(CACHE_FILE.read_text())
            age = datetime.now().timestamp() - data.get("timestamp", 0)
            if age < CACHE_TTL_SECONDS:
                return data
    except (OSError, ValueError, KeyError):
        pass
    return None


def _cache_weather(data: dict) -> None:
    try:
        data["timestamp"] = datetime.now().timestamp()
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(data))
    except OSError:
        pass


def _get_location() -> tuple[float, float] | None:
    """Get coordinates via free IP geolocation. Falls back to None."""
    try:
        resp = requests.get("http://ip-api.com/json/", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("lat") or not data.get("lon"):
            return None, None
        return data["lat"], data["lon"]
    except (requests.RequestException, KeyError, ValueError):
        return None, None


def _geocode(location: str) -> tuple[float, float] | None:
    """Geocode a city name or zip code to coordinates using Nominatim."""
    try:
        # Nominatim usage policy requires a User-Agent: https://operations.osmfoundation.org/policies/nominatim/
        headers = {"User-Agent": USER_AGENT}
        resp = requests.get(
            f"https://nominatim.openstreetmap.org/search?q={location}&format=json&limit=1",
            headers=headers,
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        if data and len(data) > 0:
            lat = float(data[0]["lat"])
            lon = float(data[0]["lon"])
            logging.debug(f"[Weather] Geocoded '{location}' to ({lat}, {lon})")
            return lat, lon
        logging.warning(f"[Weather] Could not geocode '{location}'. No results found.")
        return None, None
    except (requests.RequestException, ValueError, KeyError) as e:
        logging.error(f"[Weather] Error during geocoding '{location}': {e}")
        return None, None


def _weather_description(code: int) -> str:
    codes = {
        0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
        45: "foggy", 48: "icy fog",
        51: "drizzling", 53: "drizzling", 55: "drizzling",
        56: "freezing drizzle", 57: "freezing drizzle",
        61: "rainy", 63: "rainy", 65: "rainy",
        66: "freezing rain", 67: "freezing rain",
        71: "snowy", 73: "snowy", 75: "snowy", 77: "snow grains",
        80: "showery", 81: "showery", 82: "showery",
        85: "snow showers", 86: "snow showers",
        95: "thunderstorms", 96: "thunderstorms with hail", 99: "thunderstorms with hail",
    }
    return codes.get(code, "unusual weather")


def _time_of_day_description(hour: int, temp: float) -> str:
    if hour < 6:
        return "early morning"
    if hour < 12:
        return "morning"
    if hour < 17:
        if temp >= 90:
            return "hot afternoon"
        if temp >= 80:
            return "warm afternoon"
        return "afternoon"
    if hour < 21:
        return "evening"
    return "night"


def fetch_weather() -> dict:
    """Fetch current weather for the user's location.

    Returns dict with: temp, feels_like, description, time_of_day, city, hour.
    API-free: uses ip-api.com for geolocation + Open-Meteo for weather.
    """
    cached = _cached_weather()
    if cached:
        return cached

    now = datetime.now()
    result = {
        "temp": 72,
        "feels_like": 72,
        "description": "clear",
        "time_of_day": _time_of_day_description(now.hour, 72),
        "city": "your area",
        "hour": now.hour,
    }

    global_config = get_config()
    weather_cfg = global_config["weather"]
    city_param = weather_cfg.get("city")
    zip_code_param = weather_cfg.get("zip_code")

    coords = None
    if city_param:
        coords = _geocode(city_param)
        if not coords:
            logging.warning(f"[Weather] Failed to geocode city '{city_param}'. Falling back to IP geolocation.")
    elif zip_code_param:
        # For now, we'll treat zip code as a city for Nominatim, but it might not be accurate.
        # A dedicated zip code to lat/lon API would be better here.
        coords = _geocode(zip_code_param)
        if not coords:
            logging.warning(f"[Weather] Failed to geocode zip code '{zip_code_param}'. Falling back to IP geolocation.")
    
    if not coords: # If city/zip_code failed or not provided, use IP geolocation
        coords = _get_location()
    if not coords:
        return result

    lat, lon = coords

    try:
        resp = requests.get(
            WEATHER_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,apparent_temperature,weather_code",
                "temperature_unit": "fahrenheit",
                "timezone": "auto",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        current = data.get("current", {})
        temp = current.get("temperature_2m", 72)
        result.update(
            temp=temp,
            feels_like=current.get("apparent_temperature", temp),
            description=_weather_description(current.get("weather_code", 0)),
            time_of_day=_time_of_day_description(now.hour, temp),
            city=data.get("timezone", "your area").split("/")[-1].replace("_", " "),
            hour=now.hour,
        )
    except (requests.RequestException, ValueError, KeyError):
        pass

    _cache_weather(result)
    return result


def format_weather_blurb(weather: dict, dj_name: str, station: str) -> str:
    """Format a weather + time announcement string for TTS playback.

    Example: "It's 3:44 on a hot sunny afternoon, 95 degrees out there.
    You're hanging out with DJ Melanie on The Groove Room."
    """
    now = datetime.now()
    ampm = "AM" if now.hour < 12 else "PM"
    h12 = now.hour % 12
    if h12 == 0:
        h12 = 12
    time_str = f"{h12}:{now.minute:02d} {ampm}"

    temp = weather.get("temp", 72)
    desc = weather.get("description", "clear")
    tod = weather.get("time_of_day", "afternoon")

    return (
        f"It's {time_str} on a {tod}, {desc} {int(temp)} degrees out there. "
        f"You're hanging out with {dj_name} on {station}."
    )


if __name__ == "__main__":
    w = fetch_weather()
    print(f"Weather: {w}")
    blurb = format_weather_blurb(w, "Morning Mike", "KPWR 105.9 FM")
    print(f"Blurb: {blurb}")