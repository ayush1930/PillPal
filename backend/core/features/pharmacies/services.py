from math import radians, sin, cos, sqrt, atan2

def distance_km(pharmacy, address):
    # Check if the user has an address
    if address is None:
        return None

    # Get the coordinates
    lat1 = address.latitude
    lon1 = address.longitude
    lat2 = pharmacy.latitude
    lon2 = pharmacy.longitude

    # Check if any coordinates are missing
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return None

    try:
        lat1 = float(lat1)
        lon1 = float(lon1)
        lat2 = float(lat2)
        lon2 = float(lon2)
    except (ValueError, TypeError):
        return None

    # Convert degrees to radians
    lat1 = radians(lat1)
    lon1 = radians(lon1)
    lat2 = radians(lat2)
    lon2 = radians(lon2)

    # Calculate the distance using the Haversine formula
    a = sin((lat2 - lat1) / 2) ** 2
    a += cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2

    a = min(1, max(0, a))

    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    # Earth's radius in miles
    distance = 6371.0 * c

    return round(distance, 1)