import math
import re

EARTH_M = 6_371_000


def distance_m(lat1, lng1, lat2, lng2):
    """Fast equirectangular distance — accurate to well under 1% at town scale."""
    x = math.radians(lng2 - lng1) * math.cos(math.radians((lat1 + lat2) / 2))
    y = math.radians(lat2 - lat1)
    return EARTH_M * math.hypot(x, y)


def nearest_town(lat, lng, towns):
    best, best_d = None, float("inf")
    for t in towns:
        d = distance_m(lat, lng, t["lat"], t["lng"])
        if d < best_d:
            best, best_d = t["name"], d
    return best


_PREFIX = re.compile(r"^(on or near)\s+", re.I)


def normalize_street(name):
    """'On or near Dock Road' -> 'DOCK ROAD'."""
    if not name:
        return ""
    s = _PREFIX.sub("", name.strip())
    s = re.sub(r"\s+", " ", s)
    return s.upper()


def pretty_street(norm):
    return " ".join(w.capitalize() if not w.isdigit() else w for w in norm.split())


# Police "street" names for non-street points — not useful door-knock targets
NON_STREETS = (
    "PARKING AREA", "SUPERMARKET", "SHOPPING AREA", "PETROL STATION", "NIGHTCLUB",
    "SPORTS/RECREATION AREA", "PARK/OPEN SPACE", "POLICE STATION", "HOSPITAL",
    "FURTHER/HIGHER EDUCATION BUILDING", "STATION", "THEATRE/CONCERT HALL",
    "BUS/COACH STATION", "AIRPORT/AIRFIELD", "CONFERENCE/EXHIBITION CENTRE",
    "PEDESTRIAN SUBWAY", "PRISON",
)


NON_STREET_WORDS = ("SERVICE AREA", "CAR PARK", "RETAIL PARK", "SHOPPING CENTRE", "INDUSTRIAL ESTATE",
                    "BUSINESS PARK", "TRADING ESTATE", "INTERCHANGE", "ROUNDABOUT", "MOTORWAY", "SLIP ROAD")


def is_door_street(norm):
    return bool(norm) and norm not in NON_STREETS and not any(w in norm for w in NON_STREET_WORDS)
