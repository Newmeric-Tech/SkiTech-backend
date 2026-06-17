"""
Geolocation Utilities

Distance calculation (Haversine formula), geofencing validation,
and coordinate helpers.
"""

import math
from typing import Tuple, Optional
from enum import Enum


class LocationStatus(str, Enum):
    INSIDE_GEOFENCE = "inside"
    OUTSIDE_GEOFENCE = "outside"
    AT_BOUNDARY = "boundary"


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float, unit: str = "meters") -> float:
    R = {'meters': 6371000, 'kilometers': 6371, 'miles': 3958.8}
    lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
    lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    return R.get(unit, R['meters']) * 2 * math.asin(math.sqrt(a))


def is_within_geofence(
    user_lat: float, user_lon: float,
    center_lat: float, center_lon: float,
    radius_meters: int,
    boundary_buffer: int = 50
) -> Tuple[bool, float, LocationStatus]:
    distance = haversine_distance(user_lat, user_lon, center_lat, center_lon, unit="meters")
    boundary_start = radius_meters - boundary_buffer
    boundary_end = radius_meters + boundary_buffer

    if distance <= boundary_start:
        return True, distance, LocationStatus.INSIDE_GEOFENCE
    elif distance <= boundary_end:
        return True, distance, LocationStatus.AT_BOUNDARY
    else:
        return False, distance, LocationStatus.OUTSIDE_GEOFENCE


def validate_coordinates(
    latitude: float, longitude: float, accuracy: Optional[float] = None
) -> Tuple[bool, Optional[str]]:
    if not (-90 <= latitude <= 90):
        return False, "Latitude must be between -90 and 90"
    if not (-180 <= longitude <= 180):
        return False, "Longitude must be between -180 and 180"
    if accuracy is not None and accuracy < 0:
        return False, "Accuracy cannot be negative"
    return True, None


def get_accuracy_warning(accuracy: Optional[float], max_accuracy: float = 100.0) -> Optional[str]:
    """Poor GPS accuracy shouldn't block a punch — just flag it for review."""
    if accuracy is not None and accuracy > max_accuracy:
        return f"Low GPS accuracy ({accuracy:.0f}m) — your location may be imprecise."
    return None


def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
    lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)
    dlon = lon2_rad - lon1_rad
    x = math.sin(dlon) * math.cos(lat2_rad)
    y = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def get_direction_description(bearing: float) -> str:
    directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                  "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return directions[int((bearing % 360 + 11.25) / 22.5) % 16]
