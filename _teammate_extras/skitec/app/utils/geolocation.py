"""
Geolocation Utilities

Provides functions for:
- Distance calculation between coordinates (Haversine formula)
- Geofencing validation
- Address geocoding/reverse geocoding
"""

import math
from typing import Tuple, Optional
from enum import Enum


class LocationStatus(str, Enum):
    """Location validation status"""
    INSIDE_GEOFENCE = "inside"
    OUTSIDE_GEOFENCE = "outside"
    AT_BOUNDARY = "boundary"


def haversine_distance(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    unit: str = "meters"
) -> float:
    """
    Calculate distance between two geographic points using Haversine formula.
    
    Args:
        lat1: Latitude of first point
        lon1: Longitude of first point
        lat2: Latitude of second point
        lon2: Longitude of second point
        unit: Unit of distance ('meters', 'kilometers', 'miles')
    
    Returns:
        Distance between two points in specified unit
        
    Example:
        >>> distance = haversine_distance(28.5244, 77.1855, 28.5250, 77.1860)
        >>> print(f"Distance: {distance:.2f} meters")
    """
    # Earth's radius in different units
    R = {
        'meters': 6371000,      # 6371 km
        'kilometers': 6371,
        'miles': 3958.8
    }
    
    # Convert degrees to radians
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    # Haversine formula
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = (
        math.sin(dlat / 2) ** 2 +
        math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))
    
    distance = R.get(unit, R['meters']) * c
    return distance


def is_within_geofence(
    user_lat: float,
    user_lon: float,
    center_lat: float,
    center_lon: float,
    radius_meters: int,
    boundary_buffer: int = 50
) -> Tuple[bool, float, LocationStatus]:
    """
    Check if user location is within geofence boundary.
    
    Args:
        user_lat: User's latitude
        user_lon: User's longitude
        center_lat: Geofence center latitude
        center_lon: Geofence center longitude
        radius_meters: Geofence radius in meters
        boundary_buffer: Buffer zone around boundary (in meters)
    
    Returns:
        Tuple of:
        - is_inside (bool): True if within geofence
        - distance (float): Distance from center in meters
        - status (LocationStatus): Detailed location status
        
    Example:
        >>> is_inside, distance, status = is_within_geofence(
        ...     28.5244, 77.1855,
        ...     28.5250, 77.1860,
        ...     500
        ... )
        >>> print(f"Inside: {is_inside}, Distance: {distance:.2f}m, Status: {status}")
    """
    distance = haversine_distance(
        user_lat, user_lon,
        center_lat, center_lon,
        unit="meters"
    )
    
    # Determine status
    boundary_start = radius_meters - boundary_buffer
    boundary_end = radius_meters + boundary_buffer
    
    if distance <= boundary_start:
        status = LocationStatus.INSIDE_GEOFENCE
        is_inside = True
    elif boundary_start < distance <= boundary_end:
        status = LocationStatus.AT_BOUNDARY
        is_inside = True  # Still consider as inside for boundary zone
    else:
        status = LocationStatus.OUTSIDE_GEOFENCE
        is_inside = False
    
    return is_inside, distance, status


def validate_coordinates(
    latitude: float,
    longitude: float,
    accuracy: Optional[float] = None,
    max_accuracy: float = 100.0
) -> Tuple[bool, Optional[str]]:
    """
    Validate GPS coordinates for plausibility.
    
    Args:
        latitude: Latitude coordinate
        longitude: Longitude coordinate
        accuracy: GPS accuracy in meters
        max_accuracy: Maximum allowed accuracy (in meters)
    
    Returns:
        Tuple of (is_valid, error_message)
        
    Example:
        >>> is_valid, error = validate_coordinates(28.5244, 77.1855, accuracy=15.0)
        >>> if is_valid:
        ...     print("Coordinates are valid")
    """
    # Check coordinate ranges
    if not (-90 <= latitude <= 90):
        return False, "Latitude must be between -90 and 90"
    
    if not (-180 <= longitude <= 180):
        return False, "Longitude must be between -180 and 180"
    
    # Check accuracy
    if accuracy is not None:
        if accuracy < 0:
            return False, "Accuracy cannot be negative"
        if accuracy > max_accuracy:
            return False, f"GPS accuracy {accuracy}m exceeds maximum {max_accuracy}m"
    
    return True, None


def calculate_bearing(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float
) -> float:
    """
    Calculate bearing (direction) from point 1 to point 2.
    
    Args:
        lat1: Starting point latitude
        lon1: Starting point longitude
        lat2: Ending point latitude
        lon2: Ending point longitude
    
    Returns:
        Bearing in degrees (0-360), where:
        - 0° = North
        - 90° = East
        - 180° = South
        - 270° = West
        
    Example:
        >>> bearing = calculate_bearing(28.5244, 77.1855, 28.5250, 77.1860)
        >>> print(f"Bearing: {bearing:.2f}°")
    """
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    dlon = lon2_rad - lon1_rad
    
    x = math.sin(dlon) * math.cos(lat2_rad)
    y = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dlon)
    
    bearing_rad = math.atan2(x, y)
    bearing_deg = math.degrees(bearing_rad)
    
    # Normalize to 0-360
    bearing_deg = (bearing_deg + 360) % 360
    
    return bearing_deg


def get_direction_description(bearing: float) -> str:
    """
    Get human-readable direction from bearing angle.
    
    Args:
        bearing: Bearing in degrees (0-360)
    
    Returns:
        Direction description (N, NE, E, SE, S, SW, W, NW)
        
    Example:
        >>> direction = get_direction_description(45)
        >>> print(f"Direction: {direction}")  # Output: NE
    """
    directions = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"
    ]
    # Normalize bearing to 0-360
    bearing = bearing % 360
    # Calculate index (each direction is 22.5 degrees)
    index = int((bearing + 11.25) / 22.5)
    return directions[index % 16]


def get_coordinates_summary(
    latitude: float,
    longitude: float,
    accuracy: Optional[float] = None
) -> dict:
    """
    Generate summary of geolocation data.
    
    Args:
        latitude: Latitude coordinate
        longitude: Longitude coordinate
        accuracy: GPS accuracy in meters
    
    Returns:
        Dictionary with formatted coordinate information
        
    Example:
        >>> summary = get_coordinates_summary(28.5244, 77.1855, 15.0)
        >>> print(summary)
    """
    return {
        "latitude": round(latitude, 6),
        "longitude": round(longitude, 6),
        "accuracy_meters": accuracy,
        "formatted": f"{latitude:.6f}°N, {longitude:.6f}°E" if latitude >= 0 and longitude >= 0
                    else f"{abs(latitude):.6f}°S, {abs(longitude):.6f}°W",
    }
